import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.database import AsyncSessionLocal
from database.models import User, Card, Collection, PromoCode, Logo, CardType, LogoRarity, ServerConfig
from utils.card_spawner import CardSpawner
from datetime import datetime, timedelta
import random

class AdminCog(commands.Cog):
    """Admin commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.card_spawner = CardSpawner(bot)
    
    @app_commands.command(name="admin_spawn", description="[ADMIN] Spawn 15 cards at once")
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_spawn(self, interaction: discord.Interaction):
        """Spawn multiple cards at once"""
        async with AsyncSessionLocal() as session:
            # Get server config to check spawn channel
            result = await session.execute(
                select(ServerConfig).where(ServerConfig.guild_id == interaction.guild.id)
            )
            server_config = result.scalar_one_or_none()
            
            if not server_config or not server_config.spawn_channel_id:
                await interaction.response.send_message(
                    "❌ Please configure a spawn channel first using `/configure`!",
                    ephemeral=True
                )
                return
            
            channel_id = server_config.spawn_channel_id
            
            await interaction.response.send_message("🔄 Spawning 15 cards...", ephemeral=True)
            
            # Spawn 15 cards
            for i in range(15):
                await self.card_spawner.spawn_card(session, interaction.guild.id, channel_id)
            
            embed = discord.Embed(
                title="✅ Cards Spawned!",
                description=f"Successfully spawned 15 cards in <#{channel_id}>!",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="give_user", description="[ADMIN] Give a card to a user")
    @app_commands.describe(
        user="The user to give the card to",
        card_name="Name of the card"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def give_user_card(self, interaction: discord.Interaction, 
                            user: discord.Member, card_name: str):
        """Give a specific card to a user"""
        async with AsyncSessionLocal() as session:
            # Find card
            result = await session.execute(
                select(Card).where(Card.name.ilike(f"%{card_name}%"))
            )
            card = result.scalar_one_or_none()
            
            if not card:
                await interaction.response.send_message(
                    f"❌ Card '{card_name}' not found!",
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
            
            # Add to collection
            collection_entry = Collection(
                user_id=user.id,
                card_id=card.id
            )
            session.add(collection_entry)
            
            db_user.cards_collected += 1
            
            await session.commit()
            
            embed = discord.Embed(
                title="✅ Card Given!",
                description=f"**{card.name}** has been given to {user.mention}!",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="give_club", description="[ADMIN] Give all cards from a club")
    @app_commands.describe(
        user="The user to give cards to",
        club_name="Name of the club"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def give_club(self, interaction: discord.Interaction, 
                       user: discord.Member, club_name: str):
        """Give all cards from a specific club to a user"""
        async with AsyncSessionLocal() as session:
            # Find all cards from club
            result = await session.execute(
                select(Card).where(Card.club.ilike(f"%{club_name}%"))
            )
            cards = result.scalars().all()
            
            if not cards:
                await interaction.response.send_message(
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
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="give_event", description="[ADMIN] Give all cards from an event")
    @app_commands.describe(
        user="The user to give cards to",
        event_type="Type of event (TOTW, TOTS, TOTY, etc.)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def give_event(self, interaction: discord.Interaction, 
                        user: discord.Member, event_type: str):
        """Give all cards from a specific event to a user"""
        async with AsyncSessionLocal() as session:
            # Find all event cards
            result = await session.execute(
                select(Card)
                .where(Card.card_type == CardType.EVENT)
                .where(Card.event_type.ilike(f"%{event_type}%"))
            )
            cards = result.scalars().all()
            
            if not cards:
                await interaction.response.send_message(
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
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="give_full", description="[ADMIN] Give every card except premium")
    @app_commands.describe(user="The user to give all cards to")
    @app_commands.checks.has_permissions(administrator=True)
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
    @app_commands.checks.has_permissions(administrator=True)
    async def promo_add(self, interaction: discord.Interaction, code: str, 
                       reward_type: str, card_name: str = None, max_uses: int = None):
        """Add a promo code"""
        async with AsyncSessionLocal() as session:
            # Check if code already exists
            result = await session.execute(
                select(PromoCode).where(PromoCode.code == code.upper())
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                await interaction.response.send_message(
                    "❌ This promo code already exists!",
                    ephemeral=True
                )
                return
            
            # Create reward object
            if reward_type == "card":
                if not card_name:
                    await interaction.response.send_message(
                        "❌ Please provide a card name for this reward type!",
                        ephemeral=True
                    )
                    return
                
                # Find card
                result = await session.execute(
                    select(Card).where(Card.name.ilike(f"%{card_name}%"))
                )
                card = result.scalar_one_or_none()
                
                if not card:
                    await interaction.response.send_message(
                        f"❌ Card '{card_name}' not found!",
                        ephemeral=True
                    )
                    return
                
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
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="promo_remove", description="[ADMIN] Remove a promo code")
    @app_commands.describe(code="The promo code to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def promo_remove(self, interaction: discord.Interaction, code: str):
        """Remove a promo code"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PromoCode).where(PromoCode.code == code.upper())
            )
            promo = result.scalar_one_or_none()
            
            if not promo:
                await interaction.response.send_message(
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
            
            await interaction.response.send_message(embed=embed)
    
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
    @app_commands.checks.has_permissions(administrator=True)
    async def logo_add(self, interaction: discord.Interaction, 
                      name: str, bonus: int, rarity: str):
        """Add a logo to the game"""
        if bonus not in [1, 2, 3]:
            await interaction.response.send_message(
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
                await interaction.response.send_message(
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
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="logo_remove", description="[ADMIN] Remove a logo from the game")
    @app_commands.describe(name="Name of the logo to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def logo_remove(self, interaction: discord.Interaction, name: str):
        """Remove a logo from the game"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Logo).where(Logo.name.ilike(f"%{name}%"))
            )
            logo = result.scalar_one_or_none()
            
            if not logo:
                await interaction.response.send_message(
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
            
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))

