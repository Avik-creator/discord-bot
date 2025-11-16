import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.database import AsyncSessionLocal
from database.models import User, Card, Collection, PromoCode, Logo, CardType, LogoRarity, ServerConfig
from utils.card_spawner import CardSpawner
import random
import asyncio
import logging

# Create module-level logger
logger = logging.getLogger('discord_bot')

async def is_admin_check(interaction: discord.Interaction) -> bool:
    """Check if user is admin (either Discord admin, database admin, or bot owner)"""
    user_id = interaction.user.id
    user_name = str(interaction.user)
    
    try:
        # Bot owner always has access
        if hasattr(interaction, 'client') and hasattr(interaction.client, 'is_owner'):
            try:
                if await interaction.client.is_owner(interaction.user):
                    logger.debug(f"User {user_name} ({user_id}) is bot owner - granting admin access")
                    return True
            except Exception as e:
                logger.warning(f"Error checking bot owner status for {user_id}: {e}")
        
        # Must be in a guild for Discord admin checks
        if interaction.guild is None:
            logger.debug(f"User {user_name} ({user_id}) tried to use admin command outside of guild")
            # Still check database admin status even outside guild
        else:
            guild_id = interaction.guild.id
            guild_name = interaction.guild.name
            
            # Guild owner always has access
            try:
                if interaction.guild.owner_id == interaction.user.id:
                    logger.debug(f"User {user_name} ({user_id}) is guild owner of {guild_name} - granting admin access")
                    return True
            except Exception as e:
                logger.warning(f"Error checking guild owner for {user_id} in {guild_name}: {e}")
            
            # Get member object - interaction.user should already be a Member in guild context
            member = None
            
            # Method 1: interaction.user is already a Member in guild contexts
            if isinstance(interaction.user, discord.Member):
                member = interaction.user
                logger.debug(f"Using interaction.user as Member for {user_name} ({user_id})")
            
            # Method 2: Try cache if not already a Member
            if member is None:
                try:
                    member = interaction.guild.get_member(interaction.user.id)
                    if member:
                        logger.debug(f"Found member {user_name} ({user_id}) in cache for {guild_name}")
                except Exception as e:
                    logger.debug(f"Could not get member from cache for {user_id} in {guild_name}: {e}")
            
            # Method 3: Force fetch if still None (requires members intent)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(interaction.user.id)
                    logger.debug(f"Fetched member {user_name} ({user_id}) for {guild_name}")
                except discord.NotFound:
                    logger.warning(f"Member {user_id} not found in guild {guild_name}")
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to fetch member {user_id} in guild {guild_name}")
                except Exception as e:
                    logger.warning(f"Error fetching member {user_id} in guild {guild_name}: {e}")
            
            # Check administrator permission
            if member is not None:
                try:
                    # Check if member has administrator permission
                    if hasattr(member, 'guild_permissions') and member.guild_permissions.administrator:
                        logger.debug(f"User {user_name} ({user_id}) has administrator permission in {guild_name} - granting admin access")
                        return True
                    else:
                        logger.debug(f"User {user_name} ({user_id}) does not have administrator permission in {guild_name}")
                        # Log permission value for debugging if available
                        if hasattr(member, 'guild_permissions'):
                            logger.debug(f"User {user_id} guild_permissions value: {member.guild_permissions.value}")
                except AttributeError as e:
                    logger.warning(f"Member {user_id} does not have guild_permissions attribute: {e}")
                except Exception as e:
                    logger.warning(f"Error checking administrator permission for {user_id} in {guild_name}: {e}")
            else:
                logger.warning(f"Could not get member object for {user_id} in {guild_name} - cannot check Discord admin status")
        
        # Check database admin status
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()
                if user and hasattr(user, 'is_admin') and user.is_admin:
                    logger.debug(f"User {user_name} ({user_id}) has database admin status - granting admin access")
                    return True
                else:
                    logger.debug(f"User {user_name} ({user_id}) does not have database admin status")
        except Exception as e:
            logger.error(f"Error checking database admin status for {user_id}: {e}", exc_info=True)
        
        # All checks failed
        logger.info(f"User {user_name} ({user_id}) failed all admin checks")
        return False
        
    except Exception as e:
        # Ultimate catch-all - if ANYTHING goes wrong, deny access (fail secure)
        logger.error(f"Unexpected error in is_admin_check for {user_id}: {e}", exc_info=True)
        return False

async def can_manage_admins(interaction: discord.Interaction) -> bool:
    """Check if user can manage admins (bot owner or existing admin)"""
    # Bot owner can always manage admins
    if await interaction.client.is_owner(interaction.user):
        return True
    
    # Check if user is admin (Discord or database)
    return await is_admin_check(interaction)

class AdminCog(commands.Cog):
    """Admin commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.card_spawner = CardSpawner(bot)
    
    @app_commands.command(name="admin_spawn", description="[ADMIN] Spawn 15 cards at once")
    @app_commands.check(is_admin_check)
    async def admin_spawn(self, interaction: discord.Interaction):
        """admin_spawn"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Get server config to check spawn channel
                result = await session.execute(
                    select(ServerConfig).where(ServerConfig.guild_id == interaction.guild.id)
                )
                server_config = result.scalar_one_or_none()
                
                if not server_config or not server_config.spawn_channel_id:
                    await interaction.followup.send(
                        "❌ Please configure a spawn channel first using `/configure`!",
                        ephemeral=True
                    )
                    return
                
                channel_id = server_config.spawn_channel_id
                
                # Get the channel to verify it exists and bot has permissions
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    # Try fetching the channel if not in cache
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception as e:
                        await interaction.followup.send(
                            f"❌ Could not find channel with ID {channel_id}. Please check the configured spawn channel.",
                            ephemeral=True
                        )
                        logger = logging.getLogger('discord_bot')
                        logger.error(f"Error fetching channel {channel_id}: {e}")
                        return
                
                # Check bot permissions
                if not channel.permissions_for(interaction.guild.me).send_messages:
                    await interaction.followup.send(
                        f"❌ I don't have permission to send messages in {channel.mention}!",
                        ephemeral=True
                    )
                    return
                
                await interaction.followup.send("🔄 Spawning 15 cards...", ephemeral=True)
                
                # Spawn 15 cards with a small delay between each to avoid rate limits
                spawned_count = 0
                logger = logging.getLogger('discord_bot')
                
                for i in range(15):
                    try:
                        # Use a new session for each spawn to avoid conflicts
                        async with AsyncSessionLocal() as spawn_session:
                            message = await self.card_spawner.spawn_card(
                                spawn_session, 
                                interaction.guild.id, 
                                channel_id,
                                bypass_active_check=True  # Allow multiple spawns for admin command
                            )
                            if message:
                                spawned_count += 1
                            else:
                                logger.warning(f"Failed to spawn card {i+1}/15")
                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Error spawning card {i+1}/15: {e}", exc_info=True)
                
                embed = discord.Embed(
                    title="✅ Cards Spawned!",
                    description=f"Successfully spawned {spawned_count} out of 15 cards in {channel.mention}!",
                    color=discord.Color.green() if spawned_count == 15 else discord.Color.orange()
                )
                
                if spawned_count < 15:
                    embed.add_field(
                        name="⚠️ Note",
                        value=f"{15 - spawned_count} cards failed to spawn. Check logs for details.",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in admin_spawn: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while spawning cards.",
                ephemeral=True
            )
    
    @app_commands.command(name="give_user", description="[ADMIN] Give a card to a user")
    @app_commands.describe(
        user="The user to give the card to",
        card_name="Name of the card"
    )
    @app_commands.check(is_admin_check)
    async def give_user_card(self, interaction: discord.Interaction, 
                            user: discord.Member, card_name: str):
        """give_user_card"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Find card - handle multiple matches
                result = await session.execute(
                    select(Card).where(Card.name.ilike(f"%{card_name}%"))
                )
                cards = result.scalars().all()
                
                if not cards:
                    await interaction.followup.send(
                        f"❌ Card '{card_name}' not found!",
                        ephemeral=True
                    )
                    return
                
                # If multiple matches, use the first one
                card = cards[0]
                multiple_matches_warning = None
                if len(cards) > 1:
                    # Prepare warning about multiple matches
                    matching_names = [c.name for c in cards[:5]]  # Show first 5
                    multiple_matches_warning = f"⚠️ Multiple cards found matching '{card_name}'. Using: **{card.name}**\n"
                    multiple_matches_warning += f"Other matches: {', '.join(matching_names[1:])}"
                    if len(cards) > 5:
                        multiple_matches_warning += f" (and {len(cards) - 5} more)"
                
                # Get or create user
                result = await session.execute(
                    select(User).where(User.id == user.id)
                )
                db_user = result.scalar_one_or_none()
                
                if not db_user:
                    db_user = User(id=user.id, username=user.name)
                    session.add(db_user)
                    await session.flush()
                
                # Check if user already has this card
                existing_collection = await session.execute(
                    select(Collection).where(
                        Collection.user_id == user.id,
                        Collection.card_id == card.id
                    )
                )
                if existing_collection.scalar_one_or_none():
                    await interaction.followup.send(
                        f"ℹ️ {user.mention} already has **{card.name}** in their collection!",
                        ephemeral=True
                    )
                    return
                
                # Add to collection
                collection_entry = Collection(
                    user_id=user.id,
                    card_id=card.id
                )
                session.add(collection_entry)
                
                db_user.cards_collected += 1
                
                embed = discord.Embed(
                    title="✅ Card Given!",
                    description=f"**{card.name}** has been given to {user.mention}!",
                    color=discord.Color.green()
                )
                
                # Add warning to embed if multiple matches
                if multiple_matches_warning:
                    embed.add_field(
                        name="⚠️ Note",
                        value=multiple_matches_warning,
                        inline=False
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
                    logger.error(f"Failed to send give_user_card response, rolled back transaction: {send_error}")
                    # Try to send error message (might also fail, but worth trying)
                    try:
                        await interaction.followup.send(
                            "❌ Card given but failed to display. Please check the user's collection.",
                            ephemeral=True
                        )
                    except:
                        pass
                    raise
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in give_user_card: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while giving the card.",
                ephemeral=True
            )
    
    @app_commands.command(name="give_club", description="[ADMIN] Give all cards from a club")
    @app_commands.describe(
        user="The user to give cards to",
        club_name="Name of the club"
    )
    @app_commands.check(is_admin_check)
    async def give_club(self, interaction: discord.Interaction, 
                       user: discord.Member, club_name: str):
        """give_club"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Find all cards from club
                result = await session.execute(
                    select(Card).where(Card.club.ilike(f"%{club_name}%"))
                )
                cards = result.scalars().all()
                
                if not cards:
                    await interaction.followup.send(
                        f"❌ No cards found for club '{club_name}'!",
                        ephemeral=True
                    )
                    return
                
                # Get or create user
                result = await session.execute(
                    select(User).where(User.id == user.id)
                )
                db_user = result.scalar_one_or_none()
                
                if not db_user:
                    db_user = User(id=user.id, username=user.name)
                    session.add(db_user)
                    await session.flush()
                
                # Add all cards to collection
                for card in cards:
                    collection_entry = Collection(
                        user_id=user.id,
                        card_id=card.id
                    )
                    session.add(collection_entry)
                
                db_user.cards_collected += len(cards)
                
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Club Collection Given!",
                    description=f"Given {len(cards)} cards from **{club_name}** to {user.mention}!",
                    color=discord.Color.green()
                )
                
                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in give_club: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while giving club cards.",
                ephemeral=True
            )
    
    @app_commands.command(name="give_event", description="[ADMIN] Give all cards from an event")
    @app_commands.describe(
        user="The user to give cards to",
        event_type="Type of event (TOTW, TOTS, TOTY, etc.)"
    )
    @app_commands.check(is_admin_check)
    async def give_event(self, interaction: discord.Interaction, 
                        user: discord.Member, event_type: str):
        """give_event"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Find all event cards
                result = await session.execute(
                    select(Card)
                    .where(Card.card_type == CardType.EVENT)
                    .where(Card.event_type.ilike(f"%{event_type}%"))
                )
                cards = result.scalars().all()
                
                if not cards:
                    await interaction.followup.send(
                        f"❌ No cards found for event '{event_type}'!",
                        ephemeral=True
                    )
                    return
                
                # Get or create user
                result = await session.execute(
                    select(User).where(User.id == user.id)
                )
                db_user = result.scalar_one_or_none()
                
                if not db_user:
                    db_user = User(id=user.id, username=user.name)
                    session.add(db_user)
                    await session.flush()
                
                # Add all cards to collection
                for card in cards:
                    collection_entry = Collection(
                        user_id=user.id,
                        card_id=card.id
                    )
                    session.add(collection_entry)
                
                db_user.cards_collected += len(cards)
                
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Event Collection Given!",
                    description=f"Given {len(cards)} cards from **{event_type}** event to {user.mention}!",
                    color=discord.Color.green()
                )
                
                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in give_event: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while giving event cards.",
                ephemeral=True
            )
    
    @app_commands.command(name="give_full", description="[ADMIN] Give every card except premium")
    @app_commands.describe(user="The user to give all cards to")
    @app_commands.check(is_admin_check)
    async def give_full(self, interaction: discord.Interaction, user: discord.Member):
        """Give all cards to a user"""
        await interaction.response.defer(ephemeral=True)
        
        async with AsyncSessionLocal() as session:
            # Get all cards
            result = await session.execute(select(Card))
            cards = result.scalars().all()
            
            if not cards:
                await interaction.followup.send(
                    "❌ No cards found in database!",
                    ephemeral=True
                )
                return
            
            # Get or create user
            result = await session.execute(
                select(User).where(User.id == user.id)
            )
            db_user = result.scalar_one_or_none()
            
            if not db_user:
                db_user = User(id=user.id, username=user.name)
                session.add(db_user)
                await session.flush()
            
            # Add all cards to collection
            for card in cards:
                collection_entry = Collection(
                    user_id=user.id,
                    card_id=card.id
                )
                session.add(collection_entry)
            
            db_user.cards_collected += len(cards)
            
            await session.commit()
            
            embed = discord.Embed(
                title="✅ Full Collection Given!",
                description=f"Given all {len(cards)} cards to {user.mention}!",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="promo_add", description="[ADMIN] Add a promo code")
    @app_commands.describe(
        code="The promo code",
        reward_type="Type of reward",
        card_name="Card name (if reward is a card)",
        max_uses="Maximum number of uses (optional)"
    )
    @app_commands.choices(reward_type=[
        app_commands.Choice(name="Random Base Card", value="pack_base"),
        app_commands.Choice(name="Random Icon Card", value="pack_icon"),
        app_commands.Choice(name="Random Event Card", value="pack_event"),
        app_commands.Choice(name="Specific Card", value="card"),
    ])
    @app_commands.check(is_admin_check)
    async def promo_add(self, interaction: discord.Interaction, code: str, 
                       reward_type: str, card_name: str = None, max_uses: int = None):
        """promo_add"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                # Check if code already exists
                result = await session.execute(
                    select(PromoCode).where(PromoCode.code == code.upper())
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    await interaction.followup.send(
                        "❌ This promo code already exists!",
                        ephemeral=True
                    )
                    return
                
                # Create reward object
                if reward_type == "card":
                    if not card_name:
                        await interaction.followup.send(
                            "❌ Please provide a card name for this reward type!",
                            ephemeral=True
                        )
                        return
                    
                    # Find card - handle multiple matches
                    result = await session.execute(
                        select(Card).where(Card.name.ilike(f"%{card_name}%"))
                    )
                    cards = result.scalars().all()
                    
                    if not cards:
                        await interaction.followup.send(
                            f"❌ Card '{card_name}' not found!",
                            ephemeral=True
                        )
                        return
                    
                    # If multiple matches, use the first one
                    if len(cards) > 1:
                        card = cards[0]
                        # Log warning about multiple matches
                        import logging
                        logger = logging.getLogger('discord_bot')
                        logger.warning(f"Multiple cards found for '{card_name}', using first match: {card.name}")
                    else:
                        card = cards[0]
                    
                    reward = {"type": "card", "card_id": card.id}
                else:
                    pack_type = reward_type.replace("pack_", "")
                    reward = {"type": "pack", "pack_type": pack_type}
                
                # Create promo code
                promo = PromoCode(
                    code=code.upper(),
                    reward=reward,
                    max_uses=max_uses,
                    current_uses=0,
                    used_by=[],
                    active=True
                )
                session.add(promo)
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Promo Code Added!",
                    description=f"Code: **{code.upper()}**",
                    color=discord.Color.green()
                )
                embed.add_field(name="Reward", value=reward_type, inline=True)
                if max_uses:
                    embed.add_field(name="Max Uses", value=str(max_uses), inline=True)
                
                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in promo_add: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while adding the promo code.",
                ephemeral=True
            )
    
    @app_commands.command(name="promo_remove", description="[ADMIN] Remove a promo code")
    @app_commands.describe(code="The promo code to remove")
    @app_commands.check(is_admin_check)
    async def promo_remove(self, interaction: discord.Interaction, code: str):
        """promo_remove"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(PromoCode).where(PromoCode.code == code.upper())
                )
                promo = result.scalar_one_or_none()
                
                if not promo:
                    await interaction.followup.send(
                        "❌ Promo code not found!",
                        ephemeral=True
                    )
                    return
                
                await session.delete(promo)
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Promo Code Removed!",
                    description=f"Code **{code.upper()}** has been removed.",
                    color=discord.Color.green()
                )
                
                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in promo_remove: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while removing the promo code.",
                ephemeral=True
            )
    
    @app_commands.command(name="logo_add", description="[ADMIN] Add a logo to the game")
    @app_commands.describe(
        name="Name of the logo",
        bonus="OVR bonus (1, 2, or 3)",
        rarity="Rarity of the logo"
    )
    @app_commands.choices(rarity=[
        app_commands.Choice(name="Common (+1 OVR)", value="common"),
        app_commands.Choice(name="Rare (+2 OVR)", value="rare"),
        app_commands.Choice(name="Legendary (+3 OVR)", value="legendary"),
    ])
    @app_commands.check(is_admin_check)
    async def logo_add(self, interaction: discord.Interaction, 
                      name: str, bonus: int, rarity: str):
        """Add a logo to the game"""
        # Defer immediately to avoid interaction timeout
        await interaction.response.defer(ephemeral=False)
        
        if bonus not in [1, 2, 3]:
            await interaction.followup.send(
                "❌ Bonus must be 1, 2, or 3!",
                ephemeral=True
            )
            return
        
        async with AsyncSessionLocal() as session:
            # Check if logo exists
            result = await session.execute(
                select(Logo).where(Logo.name == name)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                await interaction.followup.send(
                    "❌ A logo with this name already exists!",
                    ephemeral=True
                )
                return
            
            # Create logo
            rarity_enum = LogoRarity[rarity.upper()]
            new_logo = Logo(
                name=name,
                rarity=rarity_enum,
                bonus=bonus
            )
            session.add(new_logo)
            await session.commit()
            
            embed = discord.Embed(
                title="✅ Logo Added!",
                description=f"**{name}** ({rarity}) - +{bonus} OVR",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="logo_remove", description="[ADMIN] Remove a logo from the game")
    @app_commands.describe(name="Name of the logo to remove")
    @app_commands.check(is_admin_check)
    async def logo_remove(self, interaction: discord.Interaction, name: str):
        """logo_remove"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Logo).where(Logo.name.ilike(f"%{name}%"))
                )
                logo = result.scalar_one_or_none()
                
                if not logo:
                    await interaction.followup.send(
                        f"❌ Logo '{name}' not found!",
                        ephemeral=True
                    )
                    return
                
                await session.delete(logo)
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Logo Removed!",
                    description=f"**{logo.name}** has been removed from the game.",
                    color=discord.Color.green()
                )
                
                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in logo_remove: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while removing the logo.",
                ephemeral=True
            )
    
    @app_commands.command(name="admin_manage", description="[ADMIN] Grant or revoke admin status to a user")
    @app_commands.describe(
        user="The user to grant or revoke admin status",
        action="Grant or revoke admin status"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Grant Admin", value="grant"),
        app_commands.Choice(name="Revoke Admin", value="revoke"),
    ])
    async def admin_manage(self, interaction: discord.Interaction, user: discord.User, action: str):
        """Manage admin status for users"""
        # Check if user can manage admins
        if not await can_manage_admins(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to manage admins! Only bot owners and existing admins can use this command.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            async with AsyncSessionLocal() as session:
                # Get or create user
                result = await session.execute(
                    select(User).where(User.id == user.id)
                )
                db_user = result.scalar_one_or_none()
                
                if not db_user:
                    db_user = User(id=user.id, username=user.name, is_admin=False)
                    session.add(db_user)
                    await session.flush()
                
                if action == "grant":
                    if db_user.is_admin:
                        await interaction.followup.send(
                            f"ℹ️ {user.mention} is already an admin!",
                            ephemeral=True
                        )
                        return
                    
                    db_user.is_admin = True
                    embed = discord.Embed(
                        title="✅ Admin Granted!",
                        description=f"**{user.mention}** has been granted admin status!",
                        color=discord.Color.green()
                    )
                else:  # revoke
                    if not db_user.is_admin:
                        await interaction.followup.send(
                            f"ℹ️ {user.mention} is not an admin!",
                            ephemeral=True
                        )
                        return
                    
                    # Prevent revoking your own admin status (unless you're bot owner)
                    if user.id == interaction.user.id and not await interaction.client.is_owner(interaction.user):
                        await interaction.followup.send(
                            "❌ You cannot revoke your own admin status!",
                            ephemeral=True
                        )
                        return
                    
                    db_user.is_admin = False
                    embed = discord.Embed(
                        title="✅ Admin Revoked!",
                        description=f"**{user.mention}** has had their admin status revoked.",
                        color=discord.Color.orange()
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
                    logger.error(f"Failed to send admin_manage response, rolled back transaction: {send_error}")
                    # Try to send error message (might also fail, but worth trying)
                    try:
                        await interaction.followup.send(
                            "❌ Admin status updated but failed to display.",
                            ephemeral=True
                        )
                    except:
                        pass
                    raise
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in admin_manage: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while managing admin status.",
                ephemeral=True
            )
    
    @app_commands.command(name="sync_commands", description="[ADMIN] Sync bot commands to this server")
    @app_commands.check(is_admin_check)
    async def sync_commands(self, interaction: discord.Interaction):
        """Sync commands to the current server"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Copy global commands to this guild's tree first
            self.bot.tree.copy_global_to(guild=interaction.guild)
            synced = await self.bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(
                f"✅ Synced {len(synced)} command(s) to this server!\n"
                f"Commands should appear within a few seconds.",
                ephemeral=True
            )
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error syncing commands: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Failed to sync commands: {str(e)}",
                ephemeral=True
            )
    
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle app command errors for this cog"""
        if isinstance(error, app_commands.CheckFailure):
            # Provide helpful error message when admin check fails
            logger.info(f"Admin check failed for user {interaction.user.id} ({interaction.user}) in command {interaction.command.name if interaction.command else 'unknown'}")
            
            # Try to send an error message
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ You don't have permission to use this command!\n\n"
                        "**To use admin commands, you need one of the following:**\n"
                        "• Discord Server Administrator permission\n"
                        "• Guild Owner status\n"
                        "• Database admin status (granted via `/admin_manage`)\n"
                        "• Bot Owner status",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ You don't have permission to use this command!\n\n"
                        "**To use admin commands, you need one of the following:**\n"
                        "• Discord Server Administrator permission\n"
                        "• Guild Owner status\n"
                        "• Database admin status (granted via `/admin_manage`)\n"
                        "• Bot Owner status",
                        ephemeral=True
                    )
            except Exception as e:
                logger.error(f"Error sending CheckFailure message: {e}", exc_info=True)
            return  # Don't re-raise, we've handled it
        
        # For other errors, log and let the global handler deal with it
        logger.error(f"Unhandled app command error in AdminCog: {error}", exc_info=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))

