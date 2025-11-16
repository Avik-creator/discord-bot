import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.database import AsyncSessionLocal
from database.models import User, Card, Collection, PromoCode, CardType
from utils.embeds import EmbedBuilder
from utils.api_football import APIFootball
from datetime import datetime, timedelta
import config

class CollectionCog(commands.Cog):
    """Collection and pack commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_football = APIFootball()
    
    async def _check_cooldown(self, user: User, cooldown_type: str) -> tuple[bool, int]:
        """Check if cooldown has expired. Returns (can_use, seconds_remaining)"""
        cooldown_field = f"{cooldown_type}_cooldown"
        last_use = getattr(user, cooldown_field, None)
        
        if last_use is None:
            return True, 0
        
        cooldown_duration = config.COOLDOWNS.get(cooldown_type, 0)
        # Use discord.utils.utcnow() for timezone-aware datetime
        now = discord.utils.utcnow()
        # Ensure last_use is timezone-aware (if it's naive, make it aware)
        if last_use.tzinfo is None:
            from datetime import timezone
            last_use = last_use.replace(tzinfo=timezone.utc)
        time_passed = (now - last_use).total_seconds()
        
        if time_passed >= cooldown_duration:
            return True, 0
        else:
            return False, int(cooldown_duration - time_passed)
    
    async def _give_random_card(self, session: AsyncSession, user_id: int, 
                               card_type: CardType = None) -> Card:
        """Give a random card to user (does NOT commit - caller must commit)"""
        # Get random card
        card = await self.api_football.get_random_card_from_db(session, card_type)
        
        if not card:
            return None
        
        # Add to collection
        collection_entry = Collection(
            user_id=user_id,
            card_id=card.id
        )
        session.add(collection_entry)
        
        # Update user stats
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.cards_collected += 1
        
        # DO NOT commit here - let the caller commit after interaction succeeds
        return card
    
    @app_commands.command(name="pack", description="Open a pack")
    @app_commands.describe(pack_type="Type of pack to open")
    @app_commands.choices(pack_type=[
        app_commands.Choice(name="Daily Pack (Base Players)", value="daily_pack"),
        app_commands.Choice(name="Weekly Pack (Icons)", value="weekly_pack"),
        app_commands.Choice(name="Event Pack", value="event_pack"),
        app_commands.Choice(name="Premium Pack (Icon/Event)", value="premium_pack"),
        app_commands.Choice(name="Booster Pack (Base)", value="booster_pack"),
    ])
    async def open_pack(self, interaction: discord.Interaction, pack_type: str):
        """Open different types of packs"""
        # Defer immediately to avoid timeout
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Get or create user
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    user = User(id=interaction.user.id, username=interaction.user.name)
                    session.add(user)
                    await session.flush()
                
                # Check cooldown
                can_use, seconds_remaining = await self._check_cooldown(user, pack_type)
                
                if not can_use:
                    hours = seconds_remaining // 3600
                    minutes = (seconds_remaining % 3600) // 60
                    await interaction.followup.send(
                        f"⏰ This pack is on cooldown! Try again in {hours}h {minutes}m",
                        ephemeral=True
                    )
                    return
                
                # Determine card type based on pack
                card_type_map = {
                    'daily_pack': CardType.BASE,
                    'weekly_pack': CardType.ICON,
                    'event_pack': CardType.EVENT,
                    'premium_pack': None,  # Random
                    'booster_pack': CardType.BASE,
                }
                
                card_type = card_type_map.get(pack_type)
                
                # Give random card
                card = await self._give_random_card(session, interaction.user.id, card_type)
                
                if not card:
                    await interaction.followup.send(
                        "❌ Error opening pack. Please try again later.",
                        ephemeral=True
                    )
                    return
                
                # Update cooldown
                cooldown_field = f"{pack_type}_cooldown"
                setattr(user, cooldown_field, discord.utils.utcnow())
                
                # Show card FIRST before committing
                embed = EmbedBuilder.card_embed(card, show_full=True)
                embed.title = f"📦 Pack Opened - {card.name}!"
                embed.color = discord.Color.gold()
                
                # Send interaction response - if this fails, we won't commit
                try:
                    await interaction.followup.send(embed=embed)
                    # Only commit if interaction response succeeds
                    await session.commit()
                except Exception as send_error:
                    # Rollback if interaction fails
                    await session.rollback()
                    import logging
                    logger = logging.getLogger('discord_bot')
                    logger.error(f"Failed to send pack response, rolled back transaction: {send_error}")
                    # Try to send error message (might also fail, but worth trying)
                    try:
                        await interaction.followup.send(
                            "❌ Pack opened but failed to display. Please check your collection.",
                            ephemeral=True
                        )
                    except:
                        pass
                    raise
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in open_pack: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while opening the pack. Please try again.",
                ephemeral=True
            )
    
    @app_commands.command(name="collection", description="View your card collection")
    @app_commands.describe(
        sort_by="How to sort your collection",
        event_filter="Filter by event type",
        page="Page number"
    )
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="Overall Rating", value="ovr"),
        app_commands.Choice(name="Alphabetical", value="name"),
        app_commands.Choice(name="Recently Obtained", value="date"),
    ])
    async def view_collection(self, interaction: discord.Interaction, 
                             sort_by: str = "ovr", event_filter: str = None, page: int = 1):
        """View user's card collection"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Get user
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()
            
            if not user:
                await interaction.followup.send(
                    "You don't have any cards yet! Use `/pack` or catch spawned cards.",
                    ephemeral=True
                )
                return
            
            # Get collection
            query = (
                select(Card, Collection)
                .join(Collection, Card.id == Collection.card_id)
                .where(Collection.user_id == interaction.user.id)
            )
            
            # Apply event filter
            if event_filter:
                query = query.where(Card.event_type == event_filter)
            
            # Apply sorting
            if sort_by == "ovr":
                query = query.order_by(Card.overall_rating.desc())
            elif sort_by == "name":
                query = query.order_by(Card.name)
            elif sort_by == "date":
                query = query.order_by(Collection.obtained_at.desc())
            
            result = await session.execute(query)
            card_data = result.all()
            
            if not card_data:
                await interaction.followup.send(
                    "No cards found with those filters!",
                    ephemeral=True
                )
                return
            
            cards = [card for card, _ in card_data]
            
            # Pagination
            cards_per_page = 10
            total_pages = (len(cards) + cards_per_page - 1) // cards_per_page
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * cards_per_page
            end_idx = start_idx + cards_per_page
            page_cards = cards[start_idx:end_idx]
            
            embed = EmbedBuilder.collection_embed(user, page_cards, page, total_pages, sort_by)
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in view_collection: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while loading your collection.",
                ephemeral=True
            )
    
    @app_commands.command(name="show", description="Display a specific card in detail")
    @app_commands.describe(player_name="Name of the player to show")
    async def show_card(self, interaction: discord.Interaction, player_name: str):
        """Show detailed card information"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Find card in user's collection
                result = await session.execute(
                    select(Card, Collection)
                    .join(Collection, Card.id == Collection.card_id)
                    .where(Collection.user_id == interaction.user.id)
                    .where(Card.name.ilike(f"%{player_name}%"))
                )
                card_data = result.first()
            
            if not card_data:
                await interaction.followup.send(
                    f"You don't have a card matching '{player_name}'!",
                    ephemeral=True
                )
                return
            
            card, _ = card_data
            
            embed = EmbedBuilder.card_embed(card, show_full=True)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in show_card: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while loading the card.",
                ephemeral=True
            )
    
    @app_commands.command(name="stats", description="View your statistics")
    async def view_stats(self, interaction: discord.Interaction):
        """Show user statistics"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()
            
            if not user:
                await interaction.followup.send(
                    "You don't have any stats yet! Start playing to build your profile.",
                    ephemeral=True
                )
                return
            
            embed = EmbedBuilder.stats_embed(user)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in view_stats: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while loading your stats.",
                ephemeral=True
            )
    
    @app_commands.command(name="vote", description="Vote for the bot to get a reward")
    async def vote_reward(self, interaction: discord.Interaction):
        """Give reward for voting"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Get or create user
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    user = User(id=interaction.user.id, username=interaction.user.name)
                    session.add(user)
                    await session.flush()
                
                # Check cooldown
                can_use, seconds_remaining = await self._check_cooldown(user, 'vote')
                
                if not can_use:
                    hours = seconds_remaining // 3600
                    minutes = (seconds_remaining % 3600) // 60
                    await interaction.followup.send(
                        f"⏰ You can vote again in {hours}h {minutes}m",
                        ephemeral=True
                    )
                    return
                
                # Give random base card
                card = await self._give_random_card(session, interaction.user.id, CardType.BASE)
                
                if not card:
                    await interaction.followup.send(
                        "❌ Error giving reward. Please try again later.",
                        ephemeral=True
                    )
                    return
                
                # Update cooldown
                user.vote_cooldown = discord.utils.utcnow()
                
                embed = discord.Embed(
                    title="🗳️ Thanks for Voting!",
                    description=f"You received **{card.name}** ({card.overall_rating} OVR)!",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Vote Link", value="[Vote on top.gg](https://top.gg)", inline=False)
                
                # Send interaction response - if this fails, we won't commit
                try:
                    await interaction.followup.send(embed=embed)
                    # Only commit if interaction response succeeds
                    await session.commit()
                except Exception as send_error:
                    # Rollback if interaction fails
                    await session.rollback()
                    import logging
                    logger = logging.getLogger('discord_bot')
                    logger.error(f"Failed to send vote reward response, rolled back transaction: {send_error}")
                    # Try to send error message (might also fail, but worth trying)
                    try:
                        await interaction.followup.send(
                            "❌ Reward processed but failed to display. Please check your collection.",
                            ephemeral=True
                        )
                    except:
                        pass
                    raise
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in vote_reward: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while processing your vote.",
                ephemeral=True
            )
    
    @app_commands.command(name="promo", description="Redeem a promo code")
    @app_commands.describe(code="The promo code to redeem")
    async def redeem_promo(self, interaction: discord.Interaction, code: str):
        """Redeem a promo code"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Get or create user
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    user = User(id=interaction.user.id, username=interaction.user.name)
                    session.add(user)
                    await session.flush()
                
                # Find promo code
                result = await session.execute(
                    select(PromoCode).where(PromoCode.code == code.upper())
                )
                promo = result.scalar_one_or_none()
                
                if not promo or not promo.active:
                    await interaction.followup.send(
                        "❌ Invalid or expired promo code!",
                        ephemeral=True
                    )
                    return
                
                # Check if user already used this code
                if interaction.user.id in promo.used_by:
                    await interaction.followup.send(
                        "❌ You have already used this promo code!",
                        ephemeral=True
                    )
                    return
                
                # Check max uses
                if promo.max_uses and promo.current_uses >= promo.max_uses:
                    await interaction.followup.send(
                        "❌ This promo code has reached its usage limit!",
                        ephemeral=True
                    )
                    return
                
                # Check expiration
                if promo.expires_at and discord.utils.utcnow() > promo.expires_at:
                    await interaction.followup.send(
                        "❌ This promo code has expired!",
                        ephemeral=True
                    )
                    return
                
                # Give reward based on type
                reward = promo.reward
                reward_text = ""
                
                if reward['type'] == 'card':
                    # Give specific card
                    card_id = reward.get('card_id')
                    if card_id:
                        collection_entry = Collection(
                            user_id=interaction.user.id,
                            card_id=card_id
                        )
                        session.add(collection_entry)
                        user.cards_collected += 1
                        reward_text = "You received a special card!"
                
                elif reward['type'] == 'pack':
                    # Give pack type
                    pack_type = reward.get('pack_type', 'base')
                    card_type_map = {
                        'base': CardType.BASE,
                        'icon': CardType.ICON,
                        'event': CardType.EVENT
                    }
                    card = await self._give_random_card(
                        session, interaction.user.id, 
                        card_type_map.get(pack_type, CardType.BASE)
                    )
                    if card:
                        reward_text = f"You received **{card.name}** ({card.overall_rating} OVR)!"
                
                # Update promo code usage
                promo.current_uses += 1
                if promo.used_by is None:
                    promo.used_by = []
                promo.used_by.append(interaction.user.id)
                
                embed = discord.Embed(
                    title="🎁 Promo Code Redeemed!",
                    description=reward_text,
                    color=discord.Color.gold()
                )
                
                # Send interaction response - if this fails, we won't commit
                try:
                    await interaction.followup.send(embed=embed)
                    # Only commit if interaction response succeeds
                    await session.commit()
                except Exception as send_error:
                    # Rollback if interaction fails
                    await session.rollback()
                    import logging
                    logger = logging.getLogger('discord_bot')
                    logger.error(f"Failed to send promo code response, rolled back transaction: {send_error}")
                    # Try to send error message (might also fail, but worth trying)
                    try:
                        await interaction.followup.send(
                            "❌ Promo code processed but failed to display. Please check your collection.",
                            ephemeral=True
                        )
                    except:
                        pass
                    raise
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in redeem_promo: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while redeeming the promo code.",
                ephemeral=True
            )
    
    @app_commands.command(name="buy", description="Get a link to the Patreon store")
    async def buy_link(self, interaction: discord.Interaction):
        """Show Patreon store link"""
        embed = discord.Embed(
            title="🛒 Support the Bot!",
            description=f"Visit our Patreon store to get premium packs and exclusive cards!\n\n"
                       f"[Visit Store]({config.PATREON_STORE_LINK})",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(CollectionCog(bot))

