import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.database import AsyncSessionLocal
from database.models import ServerConfig
import config

class ServerConfigCog(commands.Cog):
    """Server configuration commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="configure", description="Set the channel where cards spawn")
    @app_commands.describe(channel="The channel to spawn cards in")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configure_spawn(self, interaction: discord.Interaction, 
                             channel: discord.TextChannel = None):
        """Configure card spawn channel"""
        if channel is None:
            channel = interaction.channel
        
        async with AsyncSessionLocal() as session:
            # Get or create server config
            result = await session.execute(
                select(ServerConfig).where(ServerConfig.guild_id == interaction.guild.id)
            )
            server_config = result.scalar_one_or_none()
            
            if not server_config:
                server_config = ServerConfig(
                    guild_id=interaction.guild.id,
                    spawn_channel_id=channel.id,
                    message_count=0,
                    message_threshold=None,
                    spawn_enabled=True
                )
                session.add(server_config)
            else:
                server_config.spawn_channel_id = channel.id
                server_config.spawn_enabled = True
            
            await session.commit()
            
            embed = discord.Embed(
                title="✅ Server Configured!",
                description=f"Cards will now spawn in {channel.mention}!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Spawn Rate",
                value=f"Cards will spawn every {config.SPAWN_MESSAGE_MIN}-{config.SPAWN_MESSAGE_MAX} messages",
                inline=False
            )
            embed.add_field(
                name="Catch Time",
                value=f"Players have {config.CATCH_TIMEOUT_SECONDS} seconds to catch each card",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="toggle_spawning", description="Enable or disable card spawning")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_spawning(self, interaction: discord.Interaction):
        """Toggle card spawning on/off"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ServerConfig).where(ServerConfig.guild_id == interaction.guild.id)
            )
            server_config = result.scalar_one_or_none()
            
            if not server_config:
                await interaction.response.send_message(
                    "❌ Please configure a spawn channel first using `/configure`!",
                    ephemeral=True
                )
                return
            
            server_config.spawn_enabled = not server_config.spawn_enabled
            await session.commit()
            
            status = "enabled" if server_config.spawn_enabled else "disabled"
            
            embed = discord.Embed(
                title=f"✅ Card Spawning {status.capitalize()}!",
                description=f"Card spawning has been {status}.",
                color=discord.Color.green() if server_config.spawn_enabled else discord.Color.red()
            )
            
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerConfigCog(bot))

