import logging

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import config
from database.database import AsyncSessionLocal
from database.models import Card, Collection, Logo, Team, TeamSlot, User
from utils.embeds import EmbedBuilder
from utils.formations import FormationManager
from utils.match_helpers import is_user_in_active_match

logger = logging.getLogger("discord_bot")


class TeamCog(commands.Cog):
    """Team management commands"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="start", description="Create your team (initialize empty XI)"
    )
    async def start_team(self, interaction: discord.Interaction):
        """Initialize a new team for the user"""
        await interaction.response.defer(ephemeral=False)

        try:
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

                # Check if team already exists FOR THIS GUILD
                result = await session.execute(
                    select(Team)
                    .where(Team.user_id == interaction.user.id)
                    .where(Team.guild_id == interaction.guild.id)
                )
                existing_team = result.scalar_one_or_none()

                if existing_team:
                    await interaction.followup.send(
                        "You already have a team! Use `/team` to view it.",
                        ephemeral=True,
                    )
                    return

                # Create new team (INSIDE the with block)
                new_team = Team(
                    user_id=interaction.user.id, guild_id=interaction.guild.id
                )
                session.add(new_team)
                await session.commit()

            embed = discord.Embed(
                title="⚽ Team Created!",
                description="Your team has been initialized!\n\nNext steps:\n"
                "1. Use `/select lineup` to choose a formation\n"
                "2. Use `/player add` to add players to your team",
                color=discord.Color.green(),
            )

            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in start_team: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while creating your team.", ephemeral=True
            )

    @app_commands.command(name="select", description="Select your team formation")
    @app_commands.describe(lineup="Choose your formation")
    async def select_lineup(self, interaction: discord.Interaction, lineup: str):
        """Select team formation"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, interaction.user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ You cannot change your formation while in an active match!\n"
                        f"Please complete your match in <#{channel_id}> first.",
                        ephemeral=True,
                    )
                    return

                result = await session.execute(
                    select(Team)
                    .where(Team.user_id == interaction.user.id)
                    .where(Team.guild_id == interaction.guild.id)
                )
                team = result.scalar_one_or_none()

                if not team:
                    await interaction.followup.send(
                        "You don't have a team yet! Use `/start` to create one.",
                        ephemeral=True,
                    )
                    return

                formation = FormationManager.get_formation(lineup)
                if not formation:
                    await interaction.followup.send(
                        "Formation data is not available yet. Please choose a different lineup.",
                        ephemeral=True,
                    )
                    return

                # Update formation
                team.formation = lineup
                await session.commit()

                embed = discord.Embed(
                    title="⚽ Formation Selected!",
                    description=f"Your team formation has been set to **{formation['name']}**",
                    color=discord.Color.green(),
                )

                # Show formation positions
                positions = list(formation["positions"].keys())
                embed.add_field(
                    name="Positions", value=", ".join(positions), inline=False
                )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in select_lineup: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while selecting the formation.", ephemeral=True
            )

    @select_lineup.autocomplete("lineup")
    async def lineup_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete formations based on available configurations"""
        del interaction  # Unused
        query = (current or "").lower()
        formations = sorted(config.FORMATIONS.items(), key=lambda item: item[1]["name"])

        suggestions = []
        for key, data in formations:
            name = data["name"]
            if query and query not in name.lower():
                continue
            suggestions.append(app_commands.Choice(name=name, value=key))
            if len(suggestions) == 25:
                break

        if not suggestions:
            suggestions = [
                app_commands.Choice(name=data["name"], value=key)
                for key, data in formations[:25]
            ]

        return suggestions

    @app_commands.command(name="team", description="View your current team")
    async def view_team(self, interaction: discord.Interaction):
        """View your current team"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Get user and team
                result = await session.execute(
                    select(User).where(User.id == interaction.user.id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    await interaction.followup.send(
                        "You don't have a team yet! Use `/start` to create one.",
                        ephemeral=True,
                    )
                    return

                result = await session.execute(
                    select(Team).where(Team.user_id == interaction.user.id)
                )
                team = result.scalar_one_or_none()

                if not team:
                    await interaction.followup.send(
                        "You don't have a team yet! Use `/start` to create one.",
                        ephemeral=True,
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
                await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in view_team: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while loading your team.", ephemeral=True
            )

    @app_commands.command(name="player", description="Manage players in your team")
    @app_commands.describe(
        action="What do you want to do?",
        position="Position in the team (LW, ST, RW, etc.)",
        player_name="Name of the player",
        position2="Second position (for swap only)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Add Player", value="add"),
            app_commands.Choice(name="Remove Player", value="remove"),
            app_commands.Choice(name="Swap Players", value="swap"),
        ]
    )
    async def player_manage(
        self,
        interaction: discord.Interaction,
        action: str,
        position: str,
        player_name: str = None,
        position2: str = None,
    ):
        """player_manage"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, interaction.user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ You cannot modify your team while in an active match!\n"
                        f"Please complete your match in <#{channel_id}> first.",
                        ephemeral=True,
                    )
                    return

                # Get team WITH GUILD ISOLATION
                result = await session.execute(
                    select(Team)
                    .where(Team.user_id == interaction.user.id)
                    .where(Team.guild_id == interaction.guild.id)
                )
                team = result.scalar_one_or_none()

                if not team:
                    await interaction.followup.send(
                        "You don't have a team yet! Use `/start` to create one.",
                        ephemeral=True,
                    )
                    return

                if not team.formation:
                    await interaction.followup.send(
                        "Please select a formation first using `/select lineup`!",
                        ephemeral=True,
                    )
                    return

                position = position.upper()

                if action == "add":
                    if not player_name:
                        await interaction.followup.send(
                            "Please provide a player name!", ephemeral=True
                        )
                        return

                    # Validate position in formation
                    if not FormationManager.validate_position_in_formation(
                        position, team.formation
                    ):
                        # Get valid positions for better error message
                        formation = FormationManager.get_formation(team.formation)
                        valid_positions = (
                            list(formation["positions"].keys()) if formation else []
                        )
                        valid_positions_str = ", ".join(sorted(valid_positions))
                        await interaction.followup.send(
                            f"❌ Position **{position}** is not valid in your current formation ({formation['name'] if formation else team.formation})!\n"
                            f"Valid positions: {valid_positions_str}",
                            ephemeral=True,
                        )
                        return

                    # Find ALL matching cards in user's collection
                    result = await session.execute(
                        select(Card, Collection)
                        .join(Collection, Card.id == Collection.card_id)
                        .where(Collection.user_id == interaction.user.id)
                        .where(Card.name.ilike(f"%{player_name}%"))
                        .order_by(Card.overall_rating.desc())
                    )
                    cards_data = result.all()

                    if not cards_data:
                        await interaction.followup.send(
                            f"❌ You don't have a card matching '{player_name}' in your collection!\n"
                            f"Use `/collection` to see your available cards.",
                            ephemeral=True,
                        )
                        return

                    # Use the best match (exact > starts with > contains)
                    card = None
                    player_name_lower = player_name.lower()
                    for card_obj, _ in cards_data:
                        if card_obj.name.lower() == player_name_lower:
                            card = card_obj
                            break
                    if not card:
                        for card_obj, _ in cards_data:
                            if card_obj.name.lower().startswith(player_name_lower):
                                card = card_obj
                                break
                    if not card:
                        card = cards_data[0][0]  # Fallback to first match

                    # VALIDATE CARD POSITION MATCHES FORMATION SLOT
                    card_position = card.position.upper()
                    # Allow flexible position matching (e.g., ST can play CF, CB can play LCB/RCB)
                    position_compatibility = {
                        "GK": ["GK"],
                        "LB": ["LB", "LWB"],
                        "RB": ["RB", "RWB"],
                        "LWB": ["LWB", "LB"],
                        "RWB": ["RWB", "RB"],
                        "CB": ["CB", "LCB", "RCB"],
                        "LCB": ["LCB", "CB"],
                        "RCB": ["RCB", "CB"],
                        "CDM": ["CDM", "LDM", "RDM", "CM"],
                        "LDM": ["LDM", "CDM"],
                        "RDM": ["RDM", "CDM"],
                        "CM": ["CM", "LCM", "RCM", "CDM", "CAM"],
                        "LCM": ["LCM", "CM"],
                        "RCM": ["RCM", "CM"],
                        "CAM": ["CAM", "LAM", "RAM", "CM"],
                        "LAM": ["LAM", "CAM"],
                        "RAM": ["RAM", "CAM"],
                        "LM": ["LM", "LW"],
                        "RM": ["RM", "RW"],
                        "LW": ["LW", "LM", "ST"],
                        "RW": ["RW", "RM", "ST"],
                        "ST": ["ST", "CF", "LW", "RW"],
                        "CF": ["CF", "ST"],
                    }

                    compatible_positions = position_compatibility.get(
                        position, [position]
                    )
                    if card_position not in compatible_positions:
                        await interaction.followup.send(
                            f"❌ **{card.name}** is a **{card_position}** and cannot play at **{position}**!\n"
                            f"This position requires: {', '.join(compatible_positions)}",
                            ephemeral=True,
                        )
                        return

                    # CHECK IF CARD IS ALREADY USED IN ANOTHER SLOT
                    result = await session.execute(
                        select(TeamSlot)
                        .where(TeamSlot.team_id == team.id)
                        .where(TeamSlot.card_id == card.id)
                    )
                    existing_usage = result.scalar_one_or_none()

                    if existing_usage and existing_usage.position != position:
                        await interaction.followup.send(
                            f"❌ **{card.name}** is already in your team at position **{existing_usage.position}**!\n"
                            f"Remove it from there first, or use `/player swap` instead.",
                            ephemeral=True,
                        )
                        return

                    card_data = (card, None)

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
                            team_id=team.id, card_id=card.id, position=position
                        )
                        session.add(new_slot)

                    await session.commit()

                    embed = discord.Embed(
                        title="✅ Player Added!",
                        description=f"**{card.name}** has been added to position **{position}**",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed)

                elif action == "remove":
                    # Remove player from position
                    result = await session.execute(
                        select(TeamSlot)
                        .where(TeamSlot.team_id == team.id)
                        .where(TeamSlot.position == position)
                    )
                    slot = result.scalar_one_or_none()

                    if not slot:
                        await interaction.followup.send(
                            f"❌ No player at position {position}!", ephemeral=True
                        )
                        return

                    await session.delete(slot)
                    await session.commit()

                    embed = discord.Embed(
                        title="✅ Player Removed!",
                        description=f"Player has been removed from position **{position}**",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed)

                elif action == "swap":
                    if not position2:
                        await interaction.followup.send(
                            "Please provide a second position to swap with!",
                            ephemeral=True,
                        )
                        return

                    position2 = position2.upper()

                    # Get both slots
                    result = await session.execute(
                        select(TeamSlot)
                        .where(TeamSlot.team_id == team.id)
                        .where(TeamSlot.position.in_([position, position2]))
                    )
                    slots = result.scalars().all()

                    if len(slots) != 2:
                        await interaction.followup.send(
                            "❌ Both positions must have players to swap!",
                            ephemeral=True,
                        )
                        return

                    # Find which slot is which position
                    slot1 = next((s for s in slots if s.position == position), None)
                    slot2 = next((s for s in slots if s.position == position2), None)

                    if not slot1 or not slot2:
                        await interaction.followup.send(
                            "❌ Could not find both positions!", ephemeral=True
                        )
                        return

                    # Swap card IDs
                    slot1.card_id, slot2.card_id = slot2.card_id, slot1.card_id
                    await session.commit()

                    embed = discord.Embed(
                        title="✅ Players Swapped!",
                        description=f"Players at positions **{position}** and **{position2}** have been swapped",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in player_manage: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while managing players.", ephemeral=True
            )

    def _get_position_suggestions(self, team, query: str):
        """Helper method to get position suggestions"""
        suggestions = []

        if team and team.formation:
            # Get valid positions from current formation
            formation = FormationManager.get_formation(team.formation)
            if formation:
                valid_positions = list(formation["positions"].keys())

                # Filter by query if provided
                if query:
                    valid_positions = [pos for pos in valid_positions if query in pos]

                # Sort positions logically (GK first, then defense, midfield, attack)
                position_order = {
                    "GK": 0,
                    "LB": 1,
                    "LWB": 2,
                    "LCB": 3,
                    "CB": 4,
                    "RCB": 5,
                    "RWB": 6,
                    "RB": 7,
                    "LDM": 8,
                    "CDM": 9,
                    "RDM": 10,
                    "LM": 11,
                    "LCM": 12,
                    "CM": 13,
                    "RCM": 14,
                    "RM": 15,
                    "LAM": 16,
                    "CAM": 17,
                    "RAM": 18,
                    "LW": 19,
                    "ST": 20,
                    "CF": 21,
                    "RW": 22,
                }

                valid_positions.sort(key=lambda x: (position_order.get(x, 99), x))

                for pos in valid_positions[:25]:  # Discord limit
                    suggestions.append(app_commands.Choice(name=pos, value=pos))
        else:
            # No formation selected, show all valid positions
            all_positions = config.VALID_POSITIONS.copy()

            # Filter by query if provided
            if query:
                all_positions = [pos for pos in all_positions if query in pos]

            for pos in all_positions[:25]:  # Discord limit
                suggestions.append(app_commands.Choice(name=pos, value=pos))

        return suggestions

    @player_manage.autocomplete("position")
    async def position_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        """Autocomplete positions based on user's current formation"""
        if not current:
            current = ""

        query = current.upper().strip()

        try:
            async with AsyncSessionLocal() as session:
                # Get user's team to check formation
                result = await session.execute(
                    select(Team).where(Team.user_id == interaction.user.id)
                )
                team = result.scalar_one_or_none()

                return self._get_position_suggestions(team, query)
        except Exception as e:
            logger.error(f"Error in position_autocomplete: {e}", exc_info=True)
            # Fallback to common positions
            common_positions = [
                "GK",
                "LB",
                "LCB",
                "RCB",
                "RB",
                "LCM",
                "CM",
                "RCM",
                "LW",
                "ST",
                "RW",
            ]
            return [
                app_commands.Choice(name=pos, value=pos)
                for pos in common_positions
                if not current or current.upper() in pos
            ]

    @player_manage.autocomplete("position2")
    async def position2_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        """Autocomplete second position for swap action"""
        if not current:
            current = ""

        query = current.upper().strip()

        try:
            async with AsyncSessionLocal() as session:
                # Get user's team to check formation WITH GUILD ISOLATION
                result = await session.execute(
                    select(Team)
                    .where(Team.user_id == interaction.user.id)
                    .where(Team.guild_id == interaction.guild.id)
                )
                team = result.scalar_one_or_none()

                return self._get_position_suggestions(team, query)
        except Exception as e:
            logger.error(f"Error in position2_autocomplete: {e}", exc_info=True)
            # Fallback to common positions
            common_positions = [
                "GK",
                "LB",
                "LCB",
                "RCB",
                "RB",
                "LCM",
                "CM",
                "RCM",
                "LW",
                "ST",
                "RW",
            ]
            return [
                app_commands.Choice(name=pos, value=pos)
                for pos in common_positions
                if not current or current.upper() in pos
            ]

    @player_manage.autocomplete("player_name")
    async def player_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        """Autocomplete player names from user's collection, sorted by position compatibility and OVR"""
        if not current:
            current = ""

        query = current.lower().strip()

        try:
            # Get the selected position from the interaction's namespace
            try:
                selected_position = interaction.namespace.position
                if selected_position:
                    selected_position = selected_position.upper()
            except:
                selected_position = None

            # Define position compatibility map (reduced for speed)
            position_compatibility = {
                "GK": ["GK"],
                "LB": ["LB", "LWB"],
                "RB": ["RB", "RWB"],
                "LWB": ["LWB", "LB"],
                "RWB": ["RWB", "RB"],
                "CB": ["CB", "LCB", "RCB"],
                "LCB": ["LCB", "CB"],
                "RCB": ["RCB", "CB"],
                "CDM": ["CDM", "LDM", "RDM", "CM"],
                "LDM": ["LDM", "CDM"],
                "RDM": ["RDM", "CDM"],
                "CM": ["CM", "LCM", "RCM", "CDM", "CAM"],
                "LCM": ["LCM", "CM"],
                "RCM": ["RCM", "CM"],
                "CAM": ["CAM", "LAM", "RAM", "CM"],
                "LAM": ["LAM", "CAM"],
                "RAM": ["RAM", "CAM"],
                "LM": ["LM", "LW"],
                "RM": ["RM", "RW"],
                "LW": ["LW", "LM", "ST"],
                "RW": ["RW", "RM", "ST"],
                "ST": ["ST", "CF", "LW", "RW"],
                "CF": ["CF", "ST"],
            }

            async with AsyncSessionLocal() as session:
                # Build query with position filter if available
                base_query = (
                    select(Card)
                    .join(Collection, Card.id == Collection.card_id)
                    .where(Collection.user_id == interaction.user.id)
                )

                # Add name filter if query exists
                if query:
                    base_query = base_query.where(Card.name.ilike(f"%{query}%"))

                # If position is selected, prioritize compatible positions
                if selected_position and selected_position in position_compatibility:
                    compatible_positions = position_compatibility.get(
                        selected_position, [selected_position]
                    )

                    # First try to get compatible cards
                    compatible_query = (
                        base_query.where(Card.position.in_(compatible_positions))
                        .order_by(Card.overall_rating.desc(), Card.name)
                        .limit(25)
                    )

                    result = await session.execute(compatible_query)
                    cards = result.scalars().all()

                    # If we don't have enough, add some from other positions
                    if len(cards) < 25:
                        other_query = (
                            base_query.where(~Card.position.in_(compatible_positions))
                            .order_by(Card.overall_rating.desc(), Card.name)
                            .limit(25 - len(cards))
                        )

                        result = await session.execute(other_query)
                        other_cards = result.scalars().all()
                        cards = list(cards) + list(other_cards)
                else:
                    # No position filter, just get top cards
                    base_query = base_query.order_by(
                        Card.overall_rating.desc(), Card.name
                    ).limit(25)

                    result = await session.execute(base_query)
                    cards = result.scalars().all()

                # Build suggestions
                suggestions = []
                for card in cards:
                    display_name = (
                        f"{card.name} ({card.position} - {card.overall_rating} OVR)"
                    )
                    suggestions.append(
                        app_commands.Choice(name=display_name, value=card.name)
                    )

                return suggestions
        except Exception as e:
            logger.error(f"Error in player_name_autocomplete: {e}", exc_info=True)
            return []

    @app_commands.command(name="logo", description="Manage your team logo")
    @app_commands.describe(
        action="What do you want to do?", logo_name="Name of the logo"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="View Current Logo", value="view"),
            app_commands.Choice(name="Add Logo", value="add"),
            app_commands.Choice(name="Remove Logo", value="remove"),
        ]
    )
    async def logo_manage(
        self, interaction: discord.Interaction, action: str, logo_name: str = None
    ):
        """logo_manage"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is in an active match (only for add/remove actions)
                if action in ["add", "remove"]:
                    is_in_match, channel_id = await is_user_in_active_match(
                        session, interaction.user.id
                    )
                    if is_in_match:
                        await interaction.followup.send(
                            f"⚠️ You cannot change your logo while in an active match!\n"
                            f"Please complete your match in <#{channel_id}> first.",
                            ephemeral=True,
                        )
                        return

                # Load team with logo relationship WITH GUILD ISOLATION</parameter>
                result = await session.execute(
                    select(Team)
                    .options(selectinload(Team.logo))
                    .where(Team.user_id == interaction.user.id)
                    .where(Team.guild_id == interaction.guild.id)
                )
                team = result.scalar_one_or_none()

                if not team:
                    await interaction.followup.send(
                        "You don't have a team yet! Use `/start` to create one.",
                        ephemeral=True,
                    )
                    return

                if action == "view":
                    if team.logo:
                        embed = discord.Embed(
                            title="🛡️ Your Team Logo",
                            description=f"**{team.logo.name}**\n+{team.logo.bonus} OVR Bonus",
                            color=discord.Color.blue(),
                        )
                    else:
                        embed = discord.Embed(
                            title="🛡️ Your Team Logo",
                            description="You don't have a logo yet!",
                            color=discord.Color.greyple(),
                        )

                    await interaction.followup.send(embed=embed)

                elif action == "add":
                    if not logo_name:
                        await interaction.followup.send(
                            "Please provide a logo name!", ephemeral=True
                        )
                        return

                    # Find ALL matching logos
                    result = await session.execute(
                        select(Logo)
                        .where(Logo.name.ilike(f"%{logo_name}%"))
                        .order_by(Logo.bonus.desc())
                    )
                    logos = result.scalars().all()

                    if not logos:
                        await interaction.followup.send(
                            f"❌ No logos matching '{logo_name}' found!", ephemeral=True
                        )
                        return

                    # Use best match (exact > starts with > contains)
                    logo = None
                    logo_name_lower = logo_name.lower()
                    for logo_obj in logos:
                        if logo_obj.name.lower() == logo_name_lower:
                            logo = logo_obj
                            break
                    if not logo:
                        for logo_obj in logos:
                            if logo_obj.name.lower().startswith(logo_name_lower):
                                logo = logo_obj
                                break
                    if not logo:
                        logo = logos[0]  # Fallback to first match

                    team.logo_id = logo.id
                    await session.commit()

                    embed = discord.Embed(
                        title="✅ Logo Added!",
                        description=f"**{logo.name}** has been added to your team!\n+{logo.bonus} OVR Bonus",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed)

                elif action == "remove":
                    if not team.logo:
                        await interaction.followup.send(
                            "You don't have a logo to remove!", ephemeral=True
                        )
                        return

                    team.logo_id = None
                    await session.commit()

                    embed = discord.Embed(
                        title="✅ Logo Removed!",
                        description="Your team logo has been removed",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in logo_manage: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while managing your logo.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(TeamCog(bot))
