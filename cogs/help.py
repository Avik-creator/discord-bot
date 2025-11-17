import discord
from discord import app_commands
from discord.ext import commands
from utils.embeds import EmbedBuilder
import logging

logger = logging.getLogger('discord_bot')

class HelpCog(commands.Cog):
    """Help command cog"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="help", description="Get an overview of all available commands")
    @app_commands.describe(category="Choose a category to learn more about")
    @app_commands.choices(category=[
        app_commands.Choice(name="Main Menu", value="main"),
        app_commands.Choice(name="Collection & Packs", value="collection"),
        app_commands.Choice(name="Team Management", value="team"),
        app_commands.Choice(name="Matches & Leaderboard", value="match"),
        app_commands.Choice(name="Admin Commands", value="admin"),
    ])
    async def help(self, interaction: discord.Interaction, category: str = "main"):
        """Show help information"""
        try:
            embed = discord.Embed(
                title="⚽ Football Card Bot - Help",
                color=discord.Color.blue()
            )
            
            if category == "main":
                embed.description = "Welcome to the Football Card Collection Bot! Use `/help` and select a category from the dropdown."
                embed.add_field(
                    name="📦 Collection Commands",
                    value="Select **Collection & Packs** from dropdown to learn about collecting cards",
                    inline=False
                )
                embed.add_field(
                    name="⚽ Team Commands",
                    value="Select **Team Management** from dropdown to learn about building teams",
                    inline=False
                )
                embed.add_field(
                    name="🎮 Match Commands",
                    value="Select **Matches & Leaderboard** from dropdown to learn about playing",
                    inline=False
                )
                embed.add_field(
                    name="👑 Admin Commands",
                    value="Select **Admin Commands** from dropdown (requires Administrator permissions)",
                    inline=False
                )
            
            elif category == "collection":
                embed.title = "📦 Collection & Pack Commands"
                embed.add_field(
                    name="Getting Cards",
                    value=(
                        "• Cards spawn in chat - click button and type name to catch!\n"
                        "• `/collection` - View your card collection\n"
                        "• `/show <player>` - Display a specific card in detail"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Card Statistics",
                    value="• `/stats` - View your collection statistics",
                    inline=False
                )
            
            elif category == "team":
                embed.title = "⚽ Team Management Commands"
                embed.add_field(
                    name="Team Setup",
                    value=(
                        "• `/start` - Create your team (initialize empty XI)\n"
                        "• `/select lineup:` - Choose your formation (use dropdown):\n"
                        "  - 4-3-3 Attack / 4-3-3 Defense\n"
                        "  - 4-4-2 Diamond / 4-2-4\n"
                        "  - 3-4-3 Diamond\n"
                        "• `/team` - View your current team"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Managing Players",
                    value=(
                        "• `/player action: add` - Add player to a position\n"
                        "• `/player action: remove` - Remove player from position\n"
                        "• `/player action: swap` - Swap two players\n"
                        "• Autocomplete helps you select positions and player names!"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Valid Positions",
                    value="GK • LB/RB • LCB/CB/RCB • LWB/RWB • LDM/CDM/RDM • LCM/CM/RCM • LAM/CAM/RAM • LM/RM • LW/ST/CF/RW",
                    inline=False
                )
                embed.add_field(
                    name="Team Logos",
                    value=(
                        "• `/logo action: view` - View your current logo\n"
                        "• `/logo action: add` - Add a logo (gives +1 to +3 OVR bonus)\n"
                        "• `/logo action: remove` - Remove your logo"
                    ),
                    inline=False
                )
            
            elif category == "match":
                embed.title = "🎮 Match & Leaderboard Commands"
                embed.add_field(
                    name="Playing Matches",
                    value=(
                        "• `/start_match opponent:` - Challenge another player\n"
                        "• `/pick` - View player selection menu during your turn\n"
                        "• Private DMs sent with your card options each round\n"
                        "• 11 rounds total - highest stat wins each round\n"
                        "• Odd rounds: Player 1 attacks | Even rounds: Player 2 attacks"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Match Strategy",
                    value=(
                        "• Attack stat battles Defense stat\n"
                        "• Formation and positioning matter!\n"
                        "• Each card can only be used once per match"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Leaderboard",
                    value=(
                        "• `/leaderboard` - View server rankings (public command)\n"
                        "• Win = 3 points | Draw = 1 point | Loss = 0 points"
                    ),
                    inline=False
                )
            
            elif category == "admin":
                embed.title = "👑 Admin Commands (Administrator Only)"
                embed.add_field(
                    name="Server Configuration",
                    value="• `/configure` - Set the channel where cards spawn automatically",
                    inline=False
                )
                embed.add_field(
                    name="Card Management",
                    value=(
                        "• `/admin action: spawn` - Manually spawn 15 cards in configured channel\n"
                        "• `/give user:` - Give a specific card to a user\n"
                        "• `/give club:` - Give full club collection to a user\n"
                        "• `/give event:` - Give full event collection to a user\n"
                        "• `/give full:` - Give complete base collection to a user"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Logo Management",
                    value=(
                        "• `/logo game action: add` - Add a new logo with OVR bonus\n"
                        "• `/logo game action: remove` - Remove a logo from the game"
                    ),
                    inline=False
                )
            
            else:
                # Fallback for unknown category
                embed.description = "❌ Unknown category. Please select a valid option from the dropdown."
                embed.add_field(
                    name="Available Categories",
                    value="• Main Menu\n• Collection & Packs\n• Team Management\n• Matches & Leaderboard\n• Admin Commands",
                    inline=False
                )
            
            embed.set_footer(text="Use /help and select a category from the dropdown for detailed information")
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
        except Exception as e:
            logger.error(f"Error in help command: {e}", exc_info=True)
            # Simple exception handling - try to respond if we haven't already
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while loading help. Please try again.",
                        ephemeral=True
                    )
            except:
                # If even error handling fails, just log it
                logger.error("Failed to send help error message to user")async def setup(bot):
    await bot.add_cog(HelpCog(bot))

