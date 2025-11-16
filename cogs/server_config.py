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
        await interaction.response.defer(ephemeral=False)
        
        try:
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
                    logger.error(f"Failed to send configure response, rolled back transaction: {send_error}")
                    # Try to send error message (might also fail, but worth trying)
                    try:
                        await interaction.followup.send(
                            "❌ Configuration updated but failed to display. Please check server settings.",
                            ephemeral=True
                        )
                    except:
                        pass
                    raise
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in configure_spawn: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while configuring the server.",
                ephemeral=True
            )
    
    @app_commands.command(name="toggle_spawning", description="Enable or disable card spawning")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_spawning(self, interaction: discord.Interaction):
        """toggle_spawning"""
        await interaction.response.defer(ephemeral=False)
        
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ServerConfig).where(ServerConfig.guild_id == interaction.guild.id)
                )
                server_config = result.scalar_one_or_none()
                
                if not server_config:
                    await interaction.followup.send(
                        "❌ Please configure a spawn channel first using `/configure`!",
                        ephemeral=True
                    )
                    return
                
                server_config.spawn_enabled = not server_config.spawn_enabled
                
                status = "enabled" if server_config.spawn_enabled else "disabled"
                
                embed = discord.Embed(
                    title=f"✅ Card Spawning {status.capitalize()}!",
                    description=f"Card spawning has been {status}.",
                    color=discord.Color.green() if server_config.spawn_enabled else discord.Color.red()
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
                    logger.error(f"Failed to send toggle spawning response, rolled back transaction: {send_error}")
                    # Try to send error message (might also fail, but worth trying)
                    try:
                        await interaction.followup.send(
                            "❌ Spawning status updated but failed to display. Please check server settings.",
                            ephemeral=True
                        )
                    except:
                        pass
                    raise
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in toggle_spawning: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while toggling spawning.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(ServerConfigCog(bot))

