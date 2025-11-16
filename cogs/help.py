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
        app_commands.Choice(name="Matches & Betting", value="match"),
        app_commands.Choice(name="Admin Commands", value="admin"),
    ])
    async def help(self, interaction: discord.Interaction, category: str = "main"):
        """Show help information"""
        try:
            # Respond immediately to avoid timeout
            await interaction.response.defer(ephemeral=False)
            
            embed = discord.Embed(
                title="⚽ Football Card Bot - Help",
                color=discord.Color.blue()
            )
            
            if category == "main":
                embed.description = "Welcome to the Football Card Collection Bot!"
                embed.add_field(
                    name="📦 Collection Commands",
                    value="`/help collection` - Learn about collecting cards",
                    inline=False
                )
                embed.add_field(
                    name="⚽ Team Commands",
                    value="`/help team` - Learn about team management",
                    inline=False
                )
                embed.add_field(
                    name="🎮 Match Commands",
                    value="`/help match` - Learn about matches and betting",
                    inline=False
                )
                embed.add_field(
                    name="👑 Admin Commands",
                    value="`/help admin` - Admin-only commands (requires permissions)",
                    inline=False
                )
            
            elif category == "collection":
                embed.title = "📦 Collection & Pack Commands"
                embed.add_field(
                    name="Getting Cards",
                    value=(
                        "• Cards spawn in chat - click button and type name to catch!\n"
                        "• `/pack daily` - Open a daily base player pack (24h cooldown)\n"
                        "• `/pack weekly` - Open a weekly icon pack (7 days cooldown)\n"
                        "• `/pack event` - Open a weekly event pack (7 days cooldown)\n"
                        "• `/pack premium` - Random icon/event card (2 days cooldown)\n"
                        "• `/pack booster` - Base player pack (2 days cooldown)\n"
                        "• `/vote` - Vote for the bot for a reward (24h cooldown)\n"
                        "• `/promo <code>` - Redeem a promo code"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Viewing Collection",
                    value=(
                        "• `/collection` - View your card collection\n"
                        "• `/show <player>` - Display a specific card in detail\n"
                        "• `/stats` - View your statistics"
                    ),
                    inline=False
                )
            
            elif category == "team":
                embed.title = "⚽ Team Management Commands"
                embed.add_field(
                    name="Team Setup",
                    value=(
                        "• `/start` - Create your team (opens an empty XI)\n"
                        "• `/select lineup` - Choose formation:\n"
                        "  - 4-3-3 Attack\n"
                        "  - 4-3-3 Defense\n"
                        "  - 4-4-2 Diamond\n"
                        "  - 4-2-4\n"
                        "  - 3-4-3 Diamond"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Managing Players",
                    value=(
                        "• `/player add <position> <name>` - Add player to team\n"
                        "• `/player remove <position>` - Remove player from position\n"
                        "• `/player swap <pos1> <pos2>` - Swap two players\n"
                        "• `/team` - View your current team"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Positions",
                    value="LW, ST, RW, CAM, LCM, RCM, CDM, LB, LCB, RCB, RB, GK",
                    inline=False
                )
                embed.add_field(
                    name="Logos",
                    value=(
                        "• `/logo` - View your current logo\n"
                        "• `/logo add <name>` - Add a logo (gives +1/+2/+3 OVR)\n"
                        "• `/logo remove` - Remove your logo"
                    ),
                    inline=False
                )
            
            elif category == "match":
                embed.title = "🎮 Match & Betting Commands"
                embed.add_field(
                    name="Playing Matches",
                    value=(
                        "• `/match start <user>` - Challenge another user\n"
                        "• `/select <player>` - Select a player for the current round\n"
                        "• Match system: 11 rounds, highest stat wins each round\n"
                        "• Attack plays vs Defense stat\n"
                        "• Formation and chemistry affect stats!"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Betting",
                    value=(
                        "• `/bet <user> <card_name>` - Bet a card against another user\n"
                        "• You can bet up to 3 cards in one bet\n"
                        "• Winner takes all cards!"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Leaderboard",
                    value=(
                        "• `/leaderboard` - View server rankings\n"
                        "• Win = 3 points | Draw = 1 point | Loss = 0 points"
                    ),
                    inline=False
                )
            
            elif category == "admin":
                embed.title = "👑 Admin Commands"
                embed.add_field(
                    name="Server Configuration",
                    value=(
                        "• `/configure` - Set the channel where cards spawn\n"
                        "• `/leaderboard` - View server leaderboard"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="Administrator Only",
                    value=(
                        "• `/admin spawn` - Spawn 15 cards at once\n"
                        "• `/give user <user> <card>` - Give a card to someone\n"
                        "• `/give club <user> <club>` - Give full club collection\n"
                        "• `/give event <user> <event>` - Give full event collection\n"
                        "• `/give full <user>` - Give every card (except premium)\n"
                        "• `/promo add <code> <reward>` - Add a promo code\n"
                        "• `/promo remove <code>` - Remove a promo code\n"
                        "• `/logo game add <name> <bonus>` - Add a logo with OVR bonus\n"
                        "• `/logo game remove <name>` - Remove a logo"
                    ),
                    inline=False
                )
            
            embed.set_footer(text="Use /help <category> to see detailed information")
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in help command: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while loading help. Please try again.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while loading help. Please try again.",
                    ephemeral=True
                )

async def setup(bot):
    await bot.add_cog(HelpCog(bot))

