import discord
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.models import ServerConfig, SpawnedCard, Card, Collection, User, CardType
import config

class CardSpawner:
    """Handles card spawning in Discord channels"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_spawns = {}  # {message_id: card_data}
    
    async def increment_message_count(self, session: AsyncSession, guild_id: int):
        """Increment message count and check if card should spawn"""
        # Get or create server config
        result = await session.execute(
            select(ServerConfig).where(ServerConfig.guild_id == guild_id)
        )
        server_config = result.scalar_one_or_none()
        
        if not server_config:
            return False, None
        
        if not server_config.spawn_enabled or not server_config.spawn_channel_id:
            return False, None
        
        # Increment message count
        server_config.message_count += 1
        
        # Check if threshold is set, if not, set a new random threshold
        if server_config.message_threshold is None:
            server_config.message_threshold = random.randint(
                config.SPAWN_MESSAGE_MIN,
                config.SPAWN_MESSAGE_MAX
            )
        
        # Check if we should spawn
        should_spawn = server_config.message_count >= server_config.message_threshold
        
        if should_spawn:
            # Reset counter and threshold
            server_config.message_count = 0
            server_config.message_threshold = random.randint(
                config.SPAWN_MESSAGE_MIN,
                config.SPAWN_MESSAGE_MAX
            )
            await session.commit()
            return True, server_config.spawn_channel_id
        
        await session.commit()
        return False, None
    
    async def spawn_card(self, session: AsyncSession, guild_id: int, channel_id: int) -> Optional[discord.Message]:
        """Spawn a random card in the channel"""
        try:
            # Get random card from database
            result = await session.execute(select(Card))
            cards = result.scalars().all()
            
            if not cards:
                return None
            
            card = random.choice(cards)
            
            # Get channel
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return None
            
            # Create embed
            embed = discord.Embed(
                title="⚽ A Wild Player Appeared!",
                description=f"A **{card.position}** player has spawned!\n\n"
                           f"Click the button below and type their name to catch them!",
                color=discord.Color.green()
            )
            
            # Add some hints without revealing full name
            name_hint = card.name[0] + "*" * (len(card.name) - 2) + card.name[-1]
            embed.add_field(name="Hint", value=name_hint, inline=False)
            embed.add_field(name="Position", value=card.position, inline=True)
            embed.add_field(name="Rating", value=f"{card.overall_rating} OVR", inline=True)
            
            if card.club:
                embed.add_field(name="Club", value=card.club, inline=True)
            
            embed.set_footer(text=f"You have {config.CATCH_TIMEOUT_SECONDS} seconds to catch this card!")
            
            # Create button
            view = CatchCardView(self, card, session)
            
            # Send message
            message = await channel.send(embed=embed, view=view)
            
            # Store spawned card in database
            expires_at = datetime.utcnow() + timedelta(seconds=config.CATCH_TIMEOUT_SECONDS)
            spawned_card = SpawnedCard(
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message.id,
                card_id=card.id,
                caught=False,
                expires_at=expires_at
            )
            session.add(spawned_card)
            await session.commit()
            
            # Store in active spawns
            self.active_spawns[message.id] = {
                'card': card,
                'spawned_card_id': spawned_card.id,
                'expires_at': expires_at
            }
            
            # Schedule expiration
            asyncio.create_task(self._handle_expiration(message, spawned_card.id, channel))
            
            return message
        
        except Exception as e:
            print(f"Error spawning card: {e}")
            return None
    
    async def _handle_expiration(self, message: discord.Message, spawned_card_id: int, channel):
        """Handle card spawn expiration"""
        await asyncio.sleep(config.CATCH_TIMEOUT_SECONDS)
        
        # Check if still active (not caught)
        if message.id in self.active_spawns:
            del self.active_spawns[message.id]
            
            # Update embed to show expired
            embed = discord.Embed(
                title="⚽ Card Expired",
                description="This card was not caught in time and has disappeared!",
                color=discord.Color.red()
            )
            
            try:
                await message.edit(embed=embed, view=None)
            except:
                pass
    
    async def attempt_catch(self, session: AsyncSession, message_id: int, user_id: int, 
                          username: str, guess: str) -> tuple[bool, str]:
        """
        Attempt to catch a spawned card
        Returns: (success, message)
        """
        if message_id not in self.active_spawns:
            return False, "This card is no longer available!"
        
        spawn_data = self.active_spawns[message_id]
        card = spawn_data['card']
        
        # Check if guess matches (case insensitive)
        if guess.lower().strip() != card.name.lower().strip():
            return False, f"Wrong name! Try again."
        
        # Correct guess! Give card to user
        # Get or create user
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(id=user_id, username=username)
            session.add(user)
            await session.flush()
        
        # Add card to collection
        collection_entry = Collection(
            user_id=user_id,
            card_id=card.id
        )
        session.add(collection_entry)
        
        # Update user stats
        user.cards_collected += 1
        
        # Mark spawned card as caught
        await session.execute(
            update(SpawnedCard)
            .where(SpawnedCard.id == spawn_data['spawned_card_id'])
            .values(caught=True, caught_by=user_id)
        )
        
        await session.commit()
        
        # Remove from active spawns
        del self.active_spawns[message_id]
        
        return True, f"Congratulations! You caught **{card.name}** ({card.overall_rating} OVR {card.position})!"

class CatchCardView(discord.ui.View):
    """View for catching cards"""
    
    def __init__(self, spawner: CardSpawner, card: Card, session: AsyncSession):
        super().__init__(timeout=config.CATCH_TIMEOUT_SECONDS)
        self.spawner = spawner
        self.card = card
        self.session = session
    
    @discord.ui.button(label="Catch Card!", style=discord.ButtonStyle.green, emoji="⚽")
    async def catch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle catch button click"""
        # Send modal for name input
        modal = CatchCardModal(self.spawner, self.card, self.session)
        await interaction.response.send_modal(modal)

class CatchCardModal(discord.ui.Modal, title="Catch the Card!"):
    """Modal for entering player name"""
    
    player_name = discord.ui.TextInput(
        label="Player Name",
        placeholder="Enter the player's full name...",
        required=True,
        max_length=100
    )
    
    def __init__(self, spawner: CardSpawner, card: Card, session: AsyncSession):
        super().__init__()
        self.spawner = spawner
        self.card = card
        self.session = session
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle name submission"""
        guess = self.player_name.value
        
        success, message = await self.spawner.attempt_catch(
            self.session,
            interaction.message.id,
            interaction.user.id,
            interaction.user.name,
            guess
        )
        
        if success:
            # Update original message
            embed = discord.Embed(
                title="⚽ Card Caught!",
                description=f"{interaction.user.mention} caught **{self.card.name}**!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Player", value=self.card.name, inline=True)
            embed.add_field(name="Position", value=self.card.position, inline=True)
            embed.add_field(name="Rating", value=f"{self.card.overall_rating} OVR", inline=True)
            
            await interaction.message.edit(embed=embed, view=None)
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

