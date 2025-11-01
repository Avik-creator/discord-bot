import discord
from discord.ext import commands
import asyncio
import logging
from database.database import init_db, AsyncSessionLocal
from database.models import ServerConfig
from utils.card_spawner import CardSpawner
from sqlalchemy import select
import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('discord_bot')

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

class FootballCardBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',  # Legacy prefix (we use slash commands)
            intents=intents,
            help_command=None
        )
        self.card_spawner = CardSpawner(self)
    
    async def setup_hook(self):
        """Setup hook called when bot is starting"""
        logger.info("Initializing database...")
        await init_db()
        
        logger.info("Loading cogs...")
        cogs = [
            'cogs.help',
            'cogs.team',
            'cogs.match',
            'cogs.collection',
            'cogs.admin',
            'cogs.server_config',
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded {cog}")
            except Exception as e:
                logger.error(f"Failed to load {cog}: {e}")
        
        # Sync commands
        logger.info("Syncing commands...")
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Connected to {len(self.guilds)} guild(s)')
        
        # Set bot status
        await self.change_presence(
            activity=discord.Game(name="⚽ /help | Football Cards")
        )
        
        logger.info('Bot is ready!')
    
    async def on_message(self, message: discord.Message):
        """Handle messages for card spawning"""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Only process messages in guilds
        if not message.guild:
            return
        
        # Check if this should trigger a spawn
        async with AsyncSessionLocal() as session:
            should_spawn, channel_id = await self.card_spawner.increment_message_count(
                session, message.guild.id
            )
            
            if should_spawn and channel_id:
                # Spawn card in configured channel
                try:
                    await self.card_spawner.spawn_card(session, message.guild.id, channel_id)
                    logger.info(f"Spawned card in guild {message.guild.id}")
                except Exception as e:
                    logger.error(f"Error spawning card: {e}")
        
        # Process commands (if any)
        await self.process_commands(message)
    
    async def on_guild_join(self, guild: discord.Guild):
        """Called when bot joins a new guild"""
        logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        
        # Create server config
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ServerConfig).where(ServerConfig.guild_id == guild.id)
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                server_config = ServerConfig(
                    guild_id=guild.id,
                    spawn_channel_id=None,
                    message_count=0,
                    spawn_enabled=False
                )
                session.add(server_config)
                await session.commit()
                logger.info(f"Created server config for guild {guild.id}")
        
        # Send welcome message to first available channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                embed = discord.Embed(
                    title="⚽ Thanks for adding Football Card Bot!",
                    description="Get started by using `/help` to see all available commands!",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="Setup",
                    value="1. Use `/configure` to set a spawn channel\n"
                          "2. Use `/start` to create your team\n"
                          "3. Start collecting cards!",
                    inline=False
                )
                try:
                    await channel.send(embed=embed)
                    break
                except:
                    continue
    
    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.CommandNotFound):
            return
        
        logger.error(f"Command error: {error}")
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        """Handle application command errors"""
        if isinstance(error, discord.app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command!",
                ephemeral=True
            )
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ This command is on cooldown. Try again in {error.retry_after:.1f}s",
                ephemeral=True
            )
        else:
            logger.error(f"Application command error: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while processing this command.",
                    ephemeral=True
                )

def main():
    """Main entry point"""
    # Check if token is set
    if not config.DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not set in environment variables!")
        return
    
    # Create and run bot
    bot = FootballCardBot()
    
    try:
        bot.run(config.DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()

