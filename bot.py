import discord
from discord.ext import commands
import asyncio
import logging
from database.database import init_db, AsyncSessionLocal
from database.models import ServerConfig
from utils.card_spawner import CardSpawner
from sqlalchemy import select
import config
from api_server import app

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('discord_bot')

# Bot setup
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

# Privileged intents - required for card spawning and member features
# Enable these in Discord Developer Portal: https://discord.com/developers/applications
try:
    intents.message_content = True  # Required for on_message (card spawning)
    intents.members = True  # Required for member-related features
except Exception:
    logger.warning("⚠️  Privileged intents not enabled! Some features may not work.")
    logger.warning("⚠️  Enable 'Message Content Intent' and 'Server Members Intent' in Discord Developer Portal")
    logger.warning("⚠️  Card spawning will be disabled without Message Content Intent")

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
                logger.error(f"Failed to load {cog}: {e}", exc_info=True)
        
        # Count registered commands before syncing
        command_count = len(self.tree.get_commands())
        logger.info(f"Registered {command_count} command(s) in command tree")
        
        if command_count == 0:
            logger.error("⚠️  No commands found in command tree! Check if cogs are loading correctly.")
        else:
            # List all registered commands for debugging
            command_names = [cmd.name for cmd in self.tree.get_commands()]
            logger.info(f"Registered commands: {', '.join(command_names[:10])}{'...' if len(command_names) > 10 else ''}")
        
        # Sync commands globally first
        logger.info("Syncing commands globally...")
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s) globally")
            if len(synced) == 0 and command_count > 0:
                logger.warning("⚠️  Commands are registered but sync returned 0. They may already be synced or there's a sync issue.")
            elif len(synced) == 0:
                logger.error("⚠️  No commands were synced! This might indicate a problem with command registration.")
        except Exception as e:
            logger.error(f"Failed to sync commands globally: {e}", exc_info=True)
    
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Connected to {len(self.guilds)} guild(s)')
        
        # Count registered commands
        command_count = len(self.tree.get_commands())
        logger.info(f"Command tree has {command_count} registered command(s)")
        
        # Sync commands to all guilds for faster propagation
        # Copy global commands to each guild's tree, then sync
        logger.info("Syncing commands to all guilds...")
        total_synced = 0
        for guild in self.guilds:
            try:
                # Copy global commands to this guild's tree
                self.tree.copy_global_to(guild=guild)
                # Add a small delay to avoid rate limits
                await asyncio.sleep(0.5)
                synced = await self.tree.sync(guild=guild)
                synced_count = len(synced)
                total_synced += synced_count
                if synced_count > 0:
                    logger.info(f"Synced {synced_count} command(s) to {guild.name}")
                else:
                    # 0 commands returned usually means they're already synced
                    logger.info(f"Commands already synced to {guild.name} (or no changes needed)")
            except discord.HTTPException as e:
                if e.status == 429:
                    logger.warning(f"Rate limited while syncing to {guild.name}. Commands will sync automatically.")
                else:
                    logger.error(f"Failed to sync commands to {guild.name}: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Failed to sync commands to {guild.name}: {e}", exc_info=True)
        
        # Note: total_synced == 0 is often normal if commands are already synced
        if total_synced == 0 and len(self.guilds) > 0 and command_count > 0:
            logger.info("Commands are already synced to all guilds (or syncing in background)")
            logger.info("💡 If commands don't appear, wait a few minutes or use /sync_commands")
        
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
                session, message.guild.id, message.channel.id
            )
            
            if should_spawn and channel_id:
                # Spawn card in configured channel
                try:
                    await self.card_spawner.spawn_card(session, message.guild.id, channel_id)
                    logger.info(f"Spawned card in guild {message.guild.id}, channel {channel_id}")
                except Exception as e:
                    logger.error(f"Error spawning card: {e}", exc_info=True)
        
        # Process commands (if any)
        await self.process_commands(message)
    
    async def on_guild_join(self, guild: discord.Guild):
        """Called when bot joins a new guild"""
        logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        
        # Wait a moment to ensure bot is ready
        await asyncio.sleep(1)
        
        # Sync commands to this guild immediately
        try:
            # Copy global commands to this guild's tree first
            self.tree.copy_global_to(guild=guild)
            all_commands = self.tree.get_commands(guild=guild)
            logger.info(f"Syncing {len(all_commands)} command(s) to {guild.name}...")
            synced = await self.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} command(s) to {guild.name}")
            if len(synced) == 0:
                logger.warning(f"⚠️  No commands synced to {guild.name}. This may indicate a registration issue.")
        except Exception as e:
            logger.error(f"Failed to sync commands to {guild.name}: {e}", exc_info=True)
        
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
        logger.error(f"Application command error: {error}", exc_info=True)
        
        try:
            # Handle specific error types with user-friendly messages
            if isinstance(error, discord.app_commands.MissingPermissions):
                error_msg = "❌ You don't have permission to use this command!"
            elif isinstance(error, discord.app_commands.CommandOnCooldown):
                # Format cooldown time nicely
                retry_after = int(error.retry_after)
                if retry_after < 60:
                    time_str = f"{retry_after}s"
                elif retry_after < 3600:
                    minutes = retry_after // 60
                    seconds = retry_after % 60
                    time_str = f"{minutes}m {seconds}s" if seconds > 0 else f"{minutes}m"
                elif retry_after < 86400:
                    hours = retry_after // 3600
                    minutes = (retry_after % 3600) // 60
                    time_str = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
                else:
                    days = retry_after // 86400
                    hours = (retry_after % 86400) // 3600
                    time_str = f"{days}d {hours}h" if hours > 0 else f"{days}d"
                error_msg = f"⏰ This command is on cooldown. Try again in **{time_str}**"
            elif isinstance(error, discord.app_commands.CheckFailure):
                error_msg = "❌ You don't meet the requirements to use this command."
            elif isinstance(error, discord.app_commands.CommandNotFound):
                error_msg = "❌ Command not found. Please check the command name and try again."
            elif isinstance(error, discord.Forbidden):
                error_msg = "❌ I don't have permission to perform this action. Please check my permissions."
            elif isinstance(error, discord.NotFound):
                error_msg = "❌ The requested resource was not found. It may have been deleted."
            elif isinstance(error, discord.HTTPException):
                # Provide user-friendly message for HTTP errors
                if error.status == 403:
                    error_msg = "❌ I don't have permission to perform this action."
                elif error.status == 404:
                    error_msg = "❌ The requested resource was not found."
                elif error.status == 429:
                    error_msg = "⏰ Too many requests! Please wait a moment and try again."
                elif error.status >= 500:
                    error_msg = "❌ Discord is experiencing issues. Please try again in a few moments."
                else:
                    error_msg = "❌ An error occurred while processing your request. Please try again."
            else:
                # For unknown errors, provide a generic but helpful message
                error_type = type(error).__name__
                error_msg = (
                    f"❌ An unexpected error occurred.\n"
                    f"Please try again, or contact support if the issue persists."
                )
            
            # Send the error message
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    error_msg,
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    error_msg,
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

def run_api_server():
    """Run the FastAPI server in a separate thread"""
    import threading
    import uvicorn
    
    def start_server():
        uvicorn.run(
            app,
            host=config.API_SERVER_HOST,
            port=config.API_SERVER_PORT,
            log_level="info"
        )
    
    thread = threading.Thread(target=start_server, daemon=True)
    thread.start()
    logger.info(f"API server starting on {config.API_SERVER_HOST}:{config.API_SERVER_PORT}")
    return thread

def main():
    """Main entry point"""
    # Check if token is set
    if not config.DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not set in environment variables!")
        return
    
    # Start API server in background thread
    api_thread = run_api_server()
    
    # Create and run bot (blocking)
    bot = FootballCardBot()
    
    try:
        bot.run(config.DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()

