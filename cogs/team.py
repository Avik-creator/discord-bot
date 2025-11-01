import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.database import AsyncSessionLocal
from database.models import User, Team, TeamSlot, Card, Collection, Logo
from utils.embeds import EmbedBuilder
from utils.formations import FormationManager
import config

class TeamCog(commands.Cog):
    """Team management commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="start", description="Create your team (initialize empty XI)")
    async def start_team(self, interaction: discord.Interaction):
        """Initialize a new team for the user"""
        async with AsyncSessionLocal() as session:
            # Check if user exists
            result = await session.execute(
                select(User).where(User.id == interaction.user.id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(id=interaction.user.id, username=interaction.user.name)
                session.add(user)
                await session.flush()
            
            # Check if team already exists
            result = await session.execute(
                select(Team).where(Team.user_id == interaction.user.id)
            )
            existing_team = result.scalar_one_or_none()
            
            if existing_team:
                await interaction.response.send_message(
                    "You already have a team! Use `/team` to view it.",
                    ephemeral=True
                )
                return
            
            # Create new team
            new_team = Team(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id
            )
            session.add(new_team)
            await session.commit()
            
            embed = discord.Embed(
                title="⚽ Team Created!",
                description="Your team has been initialized!\n\nNext steps:\n"
                           "1. Use `/select lineup` to choose a formation\n"
                           "2. Use `/player add` to add players to your team",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="select", description="Select your team formation")
    @app_commands.describe(lineup="Choose your formation")
    @app_commands.choices(lineup=[
        app_commands.Choice(name="4-3-3 Attack", value="433_attack"),
        app_commands.Choice(name="4-3-3 Defense", value="433_defense"),
        app_commands.Choice(name="4-4-2 Diamond", value="442_diamond"),
        app_commands.Choice(name="4-2-4", value="424"),
        app_commands.Choice(name="3-4-3 Diamond", value="343_diamond"),
    ])
    async def select_lineup(self, interaction: discord.Interaction, lineup: str):
        """Select team formation"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Team).where(Team.user_id == interaction.user.id)
            )
            team = result.scalar_one_or_none()
            
            if not team:
                await interaction.response.send_message(
                    "You don't have a team yet! Use `/start` to create one.",
                    ephemeral=True
                )
                return
            
            # Update formation
            team.formation = lineup
            await session.commit()
            
            formation = FormationManager.get_formation(lineup)
            
            embed = discord.Embed(
                title="⚽ Formation Selected!",
                description=f"Your team formation has been set to **{formation['name']}**",
                color=discord.Color.green()
            )
            
            # Show formation positions
            positions = list(formation['positions'].keys())
            embed.add_field(
                name="Positions",
                value=", ".join(positions),
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="team", description="View your current team")
    async def view_team(self, interaction: discord.Interaction):
        """Display user's team"""
        async with AsyncSessionLocal() as session:
            # Get user and team
            result = await session.execute(
                select(User).where(User.id == interaction.user.id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                await interaction.response.send_message(
                    "You don't have a team yet! Use `/start` to create one.",
                    ephemeral=True
                )
                return
            
            result = await session.execute(
                select(Team).where(Team.user_id == interaction.user.id)
            )
            team = result.scalar_one_or_none()
            
            if not team:
                await interaction.response.send_message(
                    "You don't have a team yet! Use `/start` to create one.",
                    ephemeral=True
                )
                return
            
            # Get team slots
            result = await session.execute(
                select(TeamSlot, Card)
                .join(Card, TeamSlot.card_id == Card.id)
                .where(TeamSlot.team_id == team.id)
            )
            slots = result.all()
            
            team_slots = {slot.position: card for slot, card in slots}
            
            # Get logo bonus
            logo_bonus = 0
            if team.logo:
                logo_bonus = team.logo.bonus
            
            embed = EmbedBuilder.team_embed(user, team, team_slots, logo_bonus)
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="player", description="Manage players in your team")
    @app_commands.describe(
        action="What do you want to do?",
        position="Position in the team (LW, ST, RW, etc.)",
        player_name="Name of the player",
        position2="Second position (for swap only)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add Player", value="add"),
        app_commands.Choice(name="Remove Player", value="remove"),
        app_commands.Choice(name="Swap Players", value="swap"),
    ])
    async def player_manage(self, interaction: discord.Interaction, action: str, 
                           position: str, player_name: str = None, position2: str = None):
        """Add, remove, or swap players"""
        async with AsyncSessionLocal() as session:
            # Get team
            result = await session.execute(
                select(Team).where(Team.user_id == interaction.user.id)
            )
            team = result.scalar_one_or_none()
            
            if not team:
                await interaction.response.send_message(
                    "You don't have a team yet! Use `/start` to create one.",
                    ephemeral=True
                )
                return
            
            if not team.formation:
                await interaction.response.send_message(
                    "Please select a formation first using `/select lineup`!",
                    ephemeral=True
                )
                return
            
            position = position.upper()
            
            if action == "add":
                if not player_name:
                    await interaction.response.send_message(
                        "Please provide a player name!",
                        ephemeral=True
                    )
                    return
                
                # Validate position in formation
                if not FormationManager.validate_position_in_formation(position, team.formation):
                    await interaction.response.send_message(
                        f"Position {position} is not valid in your current formation!",
                        ephemeral=True
                    )
                    return
                
                # Find card in user's collection
                result = await session.execute(
                    select(Card, Collection)
                    .join(Collection, Card.id == Collection.card_id)
                    .where(Collection.user_id == interaction.user.id)
                    .where(Card.name.ilike(f"%{player_name}%"))
                )
                card_data = result.first()
                
                if not card_data:
                    await interaction.response.send_message(
                        f"You don't have a card matching '{player_name}' in your collection!",
                        ephemeral=True
                    )
                    return
                
                card, _ = card_data
                
                # Check if position is already occupied
                result = await session.execute(
                    select(TeamSlot)
                    .where(TeamSlot.team_id == team.id)
                    .where(TeamSlot.position == position)
                )
                existing_slot = result.scalar_one_or_none()
                
                if existing_slot:
                    # Update existing slot
                    existing_slot.card_id = card.id
                else:
                    # Create new slot
                    new_slot = TeamSlot(
                        team_id=team.id,
                        card_id=card.id,
                        position=position
                    )
                    session.add(new_slot)
                
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Player Added!",
                    description=f"**{card.name}** has been added to position **{position}**",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            
            elif action == "remove":
                # Remove player from position
                result = await session.execute(
                    select(TeamSlot)
                    .where(TeamSlot.team_id == team.id)
                    .where(TeamSlot.position == position)
                )
                slot = result.scalar_one_or_none()
                
                if not slot:
                    await interaction.response.send_message(
                        f"No player at position {position}!",
                        ephemeral=True
                    )
                    return
                
                await session.delete(slot)
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Player Removed!",
                    description=f"Player has been removed from position **{position}**",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            
            elif action == "swap":
                if not position2:
                    await interaction.response.send_message(
                        "Please provide a second position to swap with!",
                        ephemeral=True
                    )
                    return
                
                position2 = position2.upper()
                
                # Get both slots
                result = await session.execute(
                    select(TeamSlot)
                    .where(TeamSlot.team_id == team.id)
                    .where(TeamSlot.position.in_([position, position2]))
                )
                slots = result.all()
                
                if len(slots) != 2:
                    await interaction.response.send_message(
                        "Both positions must have players to swap!",
                        ephemeral=True
                    )
                    return
                
                slot1, slot2 = slots[0], slots[1]
                
                # Swap card IDs
                slot1.card_id, slot2.card_id = slot2.card_id, slot1.card_id
                
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Players Swapped!",
                    description=f"Players at positions **{position}** and **{position2}** have been swapped",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="logo", description="Manage your team logo")
    @app_commands.describe(
        action="What do you want to do?",
        logo_name="Name of the logo"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="View Current Logo", value="view"),
        app_commands.Choice(name="Add Logo", value="add"),
        app_commands.Choice(name="Remove Logo", value="remove"),
    ])
    async def logo_manage(self, interaction: discord.Interaction, action: str, logo_name: str = None):
        """Manage team logo"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Team).where(Team.user_id == interaction.user.id)
            )
            team = result.scalar_one_or_none()
            
            if not team:
                await interaction.response.send_message(
                    "You don't have a team yet! Use `/start` to create one.",
                    ephemeral=True
                )
                return
            
            if action == "view":
                if team.logo:
                    embed = discord.Embed(
                        title="🛡️ Your Team Logo",
                        description=f"**{team.logo.name}**\n+{team.logo.bonus} OVR Bonus",
                        color=discord.Color.blue()
                    )
                else:
                    embed = discord.Embed(
                        title="🛡️ Your Team Logo",
                        description="You don't have a logo yet!",
                        color=discord.Color.grey()
                    )
                
                await interaction.response.send_message(embed=embed)
            
            elif action == "add":
                if not logo_name:
                    await interaction.response.send_message(
                        "Please provide a logo name!",
                        ephemeral=True
                    )
                    return
                
                # Find logo
                result = await session.execute(
                    select(Logo).where(Logo.name.ilike(f"%{logo_name}%"))
                )
                logo = result.scalar_one_or_none()
                
                if not logo:
                    await interaction.response.send_message(
                        f"Logo '{logo_name}' not found!",
                        ephemeral=True
                    )
                    return
                
                team.logo_id = logo.id
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Logo Added!",
                    description=f"**{logo.name}** has been added to your team!\n+{logo.bonus} OVR Bonus",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            
            elif action == "remove":
                if not team.logo:
                    await interaction.response.send_message(
                        "You don't have a logo to remove!",
                        ephemeral=True
                    )
                    return
                
                team.logo_id = None
                await session.commit()
                
                embed = discord.Embed(
                    title="✅ Logo Removed!",
                    description="Your team logo has been removed",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(TeamCog(bot))

