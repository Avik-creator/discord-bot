import json
import logging
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import AsyncSessionLocal
from database.models import (
    ActiveMatch,
    Bet,
    Card,
    Collection,
    Leaderboard,
    Match,
    Team,
    TeamSlot,
    User,
)
from utils.embeds import EmbedBuilder
from utils.match_engine import MatchEngine, MatchState
from utils.match_helpers import is_user_in_active_match
from utils.redis_manager import redis_manager

logger = logging.getLogger("discord_bot")


class PlayerSelectView(discord.ui.View):
    """View with select menu for picking players"""

    def __init__(
        self, match_state: MatchState, user_id: int, cog_instance, channel=None
    ):
        super().__init__(timeout=300)  # 5 minute timeout
        self.match_state = match_state
        self.user_id = user_id
        self.cog = cog_instance
        self.channel = channel  # Store channel reference for DM responses
        self.created_for_round = (
            match_state.current_round
        )  # Track which round this view is for

        # Validate user_id is one of the players
        if user_id != match_state.player1_id and user_id != match_state.player2_id:
            logger.error(
                f"PlayerSelectView: Invalid user_id {user_id}. Player1: {match_state.player1_id}, Player2: {match_state.player2_id}"
            )
            # Default to player1_team as fallback (shouldn't happen, but prevents crash)
            team = match_state.player1_team
            used_positions = match_state.player1_used_cards
            used_card_ids = match_state.player1_used_card_ids
        else:
            # Get the team directly - this is the source of truth
            if user_id == match_state.player1_id:
                team = match_state.player1_team
                used_positions = match_state.player1_used_cards
                used_card_ids = match_state.player1_used_card_ids
            else:
                team = match_state.player2_team
                used_positions = match_state.player2_used_cards
                used_card_ids = match_state.player2_used_card_ids

        # Build dropdown options directly from team, filtering out used cards
        # Use get_available_cards to ensure we're using the same logic everywhere
        available_cards = match_state.get_available_cards(user_id)

        # CRITICAL: Log available cards for debugging
        logger.info(
            f"Building dropdown for user {user_id}, round {match_state.current_round}. Available: {len(available_cards)} cards"
        )
        if user_id == match_state.player1_id:
            logger.info(
                f"Player 1 used positions: {match_state.player1_used_cards}, used card IDs: {match_state.player1_used_card_ids}"
            )
        else:
            logger.info(
                f"Player 2 used positions: {match_state.player2_used_cards}, used card IDs: {match_state.player2_used_card_ids}"
            )

        options = []
        for position, card in available_cards.items():
            # Double-check the card hasn't been used (defensive programming)
            if position in used_positions:
                logger.error(
                    f"CRITICAL: Position {position} found in available_cards but also in used_positions for user {user_id}. Skipping!"
                )
                continue

            if card.id in used_card_ids:
                logger.error(
                    f"CRITICAL: Card {card.name} (ID: {card.id}) found in available_cards but also in used_card_ids for user {user_id}. Skipping!"
                )
                continue

            # This card is available - add to dropdown
            label = card.name[:100]  # Discord limit is 100 chars
            description = (
                f"{position} - {card.attack_stat} ATK / {card.defense_stat} DEF"[:100]
            )
            options.append(
                discord.SelectOption(
                    label=label, description=description, value=position
                )
            )

        if options:
            select = discord.ui.Select(
                placeholder="Choose a player...",
                options=options[:25],  # Discord limit is 25 options
            )
            select.callback = self.on_select
            self.add_item(select)
        else:
            # No available cards - this shouldn't happen, but handle it
            select = discord.ui.Select(
                placeholder="No players available!",
                options=[
                    discord.SelectOption(
                        label="No players", value="none", description="All players used"
                    )
                ],
            )
            select.callback = self.on_select
            self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        """Handle player selection"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ This menu is not for you!", ephemeral=True
            )
            return

        # Defer immediately to prevent interaction timeout
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            # Interaction already expired or responded to
            logger.warning(f"Interaction expired for user {interaction.user.id}")
            return
        except Exception as e:
            logger.error(f"Error deferring interaction: {e}")
            return

        # Disable view immediately to prevent double-use
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass  # DM might be deleted, ignore

        # Get the match channel (either from stored reference or current channel)
        match_channel = self.channel if self.channel else interaction.channel

        # CRITICAL: Get fresh match state from Redis/memory
        current_match_state = await self.cog._get_match_state(match_channel.id)
        if not current_match_state:
            await interaction.followup.send("❌ No active match found!", ephemeral=True)
            return

        # Update our reference to the fresh state
        self.match_state = current_match_state

        # CRITICAL: Verify this is for the current round (prevent stale view usage)
        if self.created_for_round != self.match_state.current_round:
            await interaction.followup.send(
                f"❌ This menu is for Round {self.created_for_round}, but we're now on Round {self.match_state.current_round}!\n"
                f"Please use the latest menu sent to you.",
                ephemeral=True,
            )
            return

        # Verify it's still this user's turn
        if self.match_state.current_turn != self.user_id:
            await interaction.followup.send(
                "❌ It's not your turn anymore!", ephemeral=True
            )
            return

        selected_position = interaction.data["values"][0]

        # Get the card directly from the team - this is the source of truth
        if self.user_id == self.match_state.player1_id:
            team = self.match_state.player1_team
            used_positions = self.match_state.player1_used_cards
            used_card_ids = self.match_state.player1_used_card_ids
        else:
            team = self.match_state.player2_team
            used_positions = self.match_state.player2_used_cards
            used_card_ids = self.match_state.player2_used_card_ids

        # Verify the position exists in the team
        if selected_position not in team:
            await interaction.followup.send(
                f"❌ Position {selected_position} is not in your team!", ephemeral=True
            )
            return

        # Get the card from the team
        selected_card = team[selected_position]

        # Verify the card hasn't been used
        if selected_position in used_positions:
            await interaction.followup.send(
                "❌ This position has already been used in this match!", ephemeral=True
            )
            return

        if selected_card.id in used_card_ids:
            await interaction.followup.send(
                f"❌ **{selected_card.name}** has already been used in this match!",
                ephemeral=True,
            )
            return

        # Mark card as selected
        if not self.match_state.select_card(self.user_id, selected_position):
            await interaction.followup.send(
                "❌ Failed to select this card. It may have already been used!",
                ephemeral=True,
            )
            return

        # CRITICAL: Verify the card was actually marked as used
        if self.user_id == self.match_state.player1_id:
            if selected_position not in self.match_state.player1_used_cards:
                logger.error(
                    f"CRITICAL BUG: Position {selected_position} was not added to player1_used_cards after select_card!"
                )
            if selected_card.id not in self.match_state.player1_used_card_ids:
                logger.error(
                    f"CRITICAL BUG: Card {selected_card.name} (ID: {selected_card.id}) was not added to player1_used_card_ids after select_card!"
                )
        else:
            if selected_position not in self.match_state.player2_used_cards:
                logger.error(
                    f"CRITICAL BUG: Position {selected_position} was not added to player2_used_cards after select_card!"
                )
            if selected_card.id not in self.match_state.player2_used_card_ids:
                logger.error(
                    f"CRITICAL BUG: Card {selected_card.name} (ID: {selected_card.id}) was not added to player2_used_card_ids after select_card!"
                )

        # Log the selection for debugging
        logger.info(
            f"Player {self.user_id} selected card {selected_card.name} (ID: {selected_card.id}) at position {selected_position} in round {self.match_state.current_round}"
        )
        logger.info(
            f"Player {self.user_id} used positions: {self.match_state.player1_used_cards if self.user_id == self.match_state.player1_id else self.match_state.player2_used_cards}"
        )
        logger.info(
            f"Player {self.user_id} used card IDs: {self.match_state.player1_used_card_ids if self.user_id == self.match_state.player1_id else self.match_state.player2_used_card_ids}"
        )

        # Handle the selection (similar to the old pick command logic)
        # Note: interaction was already deferred at the start of this method

        # Use the selected_card from team to ensure we have the correct card name
        selected_card_name = selected_card.name

        # Check if both players have selected
        if self.user_id == self.match_state.player1_id:
            # Player 1 selected - switch turn to player 2

            # CRITICAL: Clear any stale position from previous rounds
            self.match_state.last_player1_position = None

            # CRITICAL: Store P1's selection for when P2 picks (sets are unordered!)
            self.match_state.last_player1_position = selected_position

            self.match_state.current_turn = self.match_state.player2_id

            # CRITICAL: Save updated match state to Redis
            await self.cog._save_match_state(match_channel.id, self.match_state)

            # CRITICAL: Get fresh match state from Redis
            fresh_state = await self.cog._get_match_state(match_channel.id)
            if not fresh_state:
                logger.error("Failed to retrieve fresh match state after saving!")
                return

            # Confirm to player 1
            await interaction.followup.send(
                f"✅ You selected **{selected_card_name}** ({selected_position})!",
                ephemeral=True,
            )

            # Use centralized turn announcement
            await self.cog._announce_turn(match_channel.id, fresh_state)
        else:
            # Player 2 selected, now play the round
            # Get player 1's selection from stored position
            player1_position = self.match_state.last_player1_position
            player2_position = selected_position

            if not player1_position:
                logger.error("CRITICAL BUG: Player 1 position not stored!")
                await interaction.followup.send(
                    "❌ Error: Player 1's selection was not found!", ephemeral=True
                )
                return

            logger.info(
                f"Playing round with P1 position: {player1_position}, P2 position: {player2_position}"
            )

            # Play round
            round_data = self.match_state.play_round(player1_position, player2_position)

            # DO NOT clear last_player1_position here - keep it so we can verify it was used correctly
            # It will be cleared when Player 1 makes their NEXT selection

            # CRITICAL: Save updated match state to Redis after round is played
            await self.cog._save_match_state(match_channel.id, self.match_state)

            # CRITICAL: Get fresh match state from Redis to ensure next dropdown is built with latest state
            fresh_state = await self.cog._get_match_state(match_channel.id)
            if not fresh_state:
                logger.error("Failed to retrieve fresh match state after saving!")
                return

            # Show round result PUBLICLY in channel
            player1 = await self.cog.bot.fetch_user(fresh_state.player1_id)
            player2 = await self.cog.bot.fetch_user(fresh_state.player2_id)

            embed = EmbedBuilder.match_round_embed(
                round_data, player1.name, player2.name
            )

            # Send confirmation to player 2 ephemerally
            await interaction.followup.send(
                f"✅ You selected **{selected_card_name}** ({selected_position})!",
                ephemeral=True,
            )

            # Post round result publicly
            await match_channel.send(embed=embed)

            # Check if match is complete
            if fresh_state.is_complete():
                await self.cog._complete_match(interaction, fresh_state, match_channel)
            else:
                # Use centralized turn announcement
                await self.cog._announce_turn(match_channel.id, fresh_state)


class MatchCog(commands.Cog):
    """Match and betting commands"""

    def __init__(self, bot):
        self.bot = bot
        # Fallback in-memory storage if Redis unavailable
        self.active_matches = {}  # {channel_id: MatchState}
        self.last_dropdown_sent = {}  # {channel_id: {"round": int, "users_sent": set()}} - Track dropdowns sent per user per round

    async def _get_match_state(self, channel_id: int) -> Optional[MatchState]:
        """Get match state from Redis or fallback to memory"""
        # Try Redis first
        match_state = await redis_manager.get_match_state(channel_id)
        if match_state:
            return match_state
        # Fallback to in-memory
        return self.active_matches.get(channel_id)

    async def _save_match_state(self, channel_id: int, match_state: MatchState):
        """Save match state to Redis and memory"""
        # Save to Redis
        await redis_manager.save_match_state(channel_id, match_state)
        # Also keep in memory as fallback
        self.active_matches[channel_id] = match_state

    async def _delete_match_state(self, channel_id: int):
        """Delete match state from Redis and memory"""
        await redis_manager.delete_match_state(channel_id)
        if channel_id in self.active_matches:
            del self.active_matches[channel_id]

    async def _announce_turn(self, channel_id: int, match_state: MatchState):
        """Centralized turn announcement - ONLY place to send turn notifications"""
        next_id = match_state.current_turn
        channel = self.bot.get_channel(channel_id)

        if not channel:
            logger.error(f"Cannot announce turn: channel {channel_id} not found")
            return

        await channel.send(
            f"⏳ **Round {match_state.current_round}** - <@{next_id}>, it's your turn! Check your DMs!"
        )

        await self._send_player_pick_menu(channel_id, next_id)

    async def _send_player_pick_menu(self, channel_id: int, user_id: int):
        """Send a PRIVATE (DM) pick menu to the correct player ONLY"""
        try:
            # CRITICAL: Always get fresh state from Redis first
            match_state = await self._get_match_state(channel_id)
            if not match_state:
                logger.error(f"No match state found for channel {channel_id}")
                return

            # Validate user_id is one of the players
            if user_id != match_state.player1_id and user_id != match_state.player2_id:
                logger.error(
                    f"Invalid user_id {user_id} passed to _send_player_pick_menu. Player1: {match_state.player1_id}, Player2: {match_state.player2_id}"
                )
                return

            # Validate it's the correct user's turn - CRITICAL: Only send to current player
            if match_state.current_turn != user_id:
                logger.error(
                    f"ERROR: Attempted to send pick menu to user {user_id} but current_turn is {match_state.current_turn}. Aborting to prevent showing wrong team!"
                )
                return

            # Check if already sent using Redis (with fallback to memory)
            already_sent = await redis_manager.check_and_mark_dropdown_sent(
                channel_id, match_state.current_round, user_id
            )

            if already_sent:
                logger.warning(
                    f"DUPLICATE DROPDOWN PREVENTED: Already sent dropdown for round {match_state.current_round} to user {user_id}. Skipping!"
                )
                return

            logger.info(
                f"Sending PRIVATE DM pick menu to user {user_id} for round {match_state.current_round}"
            )

            user = await self.bot.fetch_user(user_id)

            # Use get_available_cards to ensure consistency with dropdown building
            available_cards = match_state.get_available_cards(user_id)

            # Log for debugging
            logger.info(
                f"Sending PRIVATE DM to user {user_id} (name: {user.name}) for round {match_state.current_round}. Available cards: {len(available_cards)}"
            )
            if user_id == match_state.player1_id:
                logger.info(
                    f"Player 1 used positions: {match_state.player1_used_cards}, used card IDs: {match_state.player1_used_card_ids}"
                )
                logger.info(
                    f"Player 1 available positions: {list(available_cards.keys())}"
                )
            else:
                logger.info(
                    f"Player 2 used positions: {match_state.player2_used_cards}, used card IDs: {match_state.player2_used_card_ids}"
                )
                logger.info(
                    f"Player 2 available positions: {list(available_cards.keys())}"
                )

            embed = discord.Embed(
                title=f"⚽ Your Turn - Round {match_state.current_round}!",
                description=f"Select a player from the dropdown below!\n\n"
                f"🔒 **This is a private DM - your opponent cannot see this.**",
                color=discord.Color.blue(),
            )

            # Add available players info with stats
            player_list = []
            for pos, card in list(available_cards.items())[:15]:  # Show more players
                player_list.append(
                    f"**{card.name}** ({pos}) - {card.attack_stat} ATK / {card.defense_stat} DEF"
                )

            if len(available_cards) > 15:
                player_list.append(
                    f"\n... and {len(available_cards) - 15} more players available"
                )

            embed.add_field(
                name=f"📋 Your Available Players ({len(available_cards)} remaining)",
                value="\n".join(player_list) if player_list else "No players available",
                inline=False,
            )

            # Get the match channel
            match_channel = self.bot.get_channel(channel_id)

            # Set footer with channel name if available
            if match_channel and hasattr(match_channel, "name"):
                embed.set_footer(text=f"Match in #{match_channel.name}")
            else:
                embed.set_footer(text="Match in progress")

            # Create view with validated user_id and channel reference
            view = PlayerSelectView(match_state, user_id, self, match_channel)

            # SEND VIA DM - TRUE PRIVACY
            try:
                await user.send(embed=embed, view=view)
                logger.info(f"Successfully sent DM pick menu to user {user_id}")
            except discord.Forbidden:
                # User has DMs disabled - fallback to ephemeral in channel
                logger.warning(
                    f"User {user_id} has DMs disabled, sending ephemeral message instead"
                )
                if user_id == interaction.user.id:
                    # Can only send ephemeral to the user who triggered the interaction
                    await interaction.followup.send(
                        content=f"⚠️ **Enable your DMs for private picks!**",
                        embed=embed,
                        view=view,
                        ephemeral=True,
                    )
                else:
                    # Cannot send ephemeral to other user - send channel message with warning
                    await interaction.channel.send(
                        content=f"<@{user_id}> ⚠️ **Please enable your DMs!** Using public message (opponent can see your team):",
                        embed=embed,
                        view=view,
                    )
        except Exception as e:
            logger.error(f"Error sending player pick menu: {e}", exc_info=True)

    async def _get_team_data(
        self, session: AsyncSession, user_id: int
    ) -> tuple[Optional[Team], Dict]:
        """Get team and slots for a user"""
        result = await session.execute(select(Team).where(Team.user_id == user_id))
        team = result.scalar_one_or_none()

        if not team or not team.formation:
            return None, {}

        # Get team slots - order by ID to ensure consistent results
        result = await session.execute(
            select(TeamSlot, Card)
            .join(Card, TeamSlot.card_id == Card.id)
            .where(TeamSlot.team_id == team.id)
            .order_by(TeamSlot.id)
        )
        slots = result.all()

        # Build team_slots dictionary, handling any duplicate positions
        # If there are duplicates, use the first one (by ID) and log a warning
        team_slots = {}
        seen_positions = set()
        for slot, card in slots:
            if slot.position in seen_positions:
                logger.warning(
                    f"Duplicate position '{slot.position}' for user {user_id} in team {team.id}. "
                    f"Position already has card {team_slots[slot.position].name}, "
                    f"skipping duplicate with card {card.name} (slot ID: {slot.id})"
                )
                continue
            team_slots[slot.position] = card
            seen_positions.add(slot.position)

        # Ensure we have 11 players
        if len(team_slots) < 11:
            logger.warning(
                f"Team {team.id} for user {user_id} has only {len(team_slots)} players, need 11"
            )
            return team, {}

        return team, team_slots

    async def _update_leaderboard(
        self, session: AsyncSession, guild_id: int, user_id: int, won: bool, draw: bool
    ):
        """Update leaderboard entry for a user"""
        result = await session.execute(
            select(Leaderboard)
            .where(Leaderboard.guild_id == guild_id)
            .where(Leaderboard.user_id == user_id)
        )
        lb_entry = result.scalar_one_or_none()

        if not lb_entry:
            lb_entry = Leaderboard(
                guild_id=guild_id, user_id=user_id, points=0, wins=0, draws=0, losses=0
            )
            session.add(lb_entry)

        # Update stats
        if won:
            lb_entry.wins += 1
            lb_entry.points += 3
        elif draw:
            lb_entry.draws += 1
            lb_entry.points += 1
        else:
            lb_entry.losses += 1

        await session.commit()

    @app_commands.command(
        name="match", description="Start a match against another user"
    )
    @app_commands.describe(opponent="The user you want to challenge")
    async def start_match(
        self, interaction: discord.Interaction, opponent: discord.Member
    ):
        """Start a match against another user"""
        # Defer immediately to avoid interaction timeout
        await interaction.response.defer(ephemeral=False)

        # Early validation
        if opponent.bot or opponent.id == interaction.user.id:
            await interaction.followup.send(
                "❌ You can't challenge bots or yourself!", ephemeral=True
            )
            return

        # Check if there's already an active match in this channel
        existing_match = await self._get_match_state(interaction.channel_id)
        if existing_match:
            await interaction.followup.send(
                "❌ There's already an active match in this channel!", ephemeral=True
            )
            return

        try:
            async with AsyncSessionLocal() as session:
                # Check if challenger is already in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, interaction.user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ You are already in an active match in <#{channel_id}>!\n"
                        f"Please complete that match before starting a new one.",
                        ephemeral=True,
                    )
                    return

                # Check if opponent is already in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, opponent.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ {opponent.mention} is already in an active match in <#{channel_id}>!\n"
                        f"Please wait until their match is complete.",
                        ephemeral=True,
                    )
                    return

                # Get both teams
                player1_team, player1_slots = await self._get_team_data(
                    session, interaction.user.id
                )
                player2_team, player2_slots = await self._get_team_data(
                    session, opponent.id
                )

                if not player1_team or not player1_slots:
                    await interaction.followup.send(
                        "❌ You need a complete team with 11 players to play!",
                        ephemeral=True,
                    )
                    return

                if not player2_team or not player2_slots:
                    await interaction.followup.send(
                        f"❌ {opponent.mention} needs a complete team with 11 players to play!",
                        ephemeral=True,
                    )
                    return

                # Create match state
                match_state = MatchState(
                    player1_id=interaction.user.id,
                    player2_id=opponent.id,
                    player1_team=player1_slots,
                    player2_team=player2_slots,
                    player1_formation=player1_team.formation,
                    player2_formation=player2_team.formation,
                )

                # Store in Redis and active matches
                await self._save_match_state(interaction.channel_id, match_state)

                # Create active match record in database
                active_match = ActiveMatch(
                    guild_id=interaction.guild.id,
                    channel_id=interaction.channel_id,
                    player1_id=interaction.user.id,
                    player2_id=opponent.id,
                    current_round=1,
                    current_turn_player=interaction.user.id,
                    game_state={},
                )
                session.add(active_match)
                await session.commit()

                # Create PUBLIC match announcement (NO team info - that's private!)
                embed = discord.Embed(
                    title="⚽ Match Started!",
                    description=f"**{interaction.user.mention}** vs **{opponent.mention}**\n\n"
                    f"🎮 11 rounds of tactical football!",
                    color=discord.Color.blue(),
                )
                embed.add_field(
                    name="How to Play",
                    value="• Each player selects 1 card per round\n"
                    "• Odd rounds: Player 1 attacks\n"
                    "• Even rounds: Player 2 attacks\n"
                    "• Attack stat vs Defense stat determines winner\n"
                    "• Winner of most rounds wins the match!",
                    inline=False,
                )
                embed.add_field(
                    name="🔒 Privacy",
                    value="Team selections are private. Each player receives their options via ephemeral messages.",
                    inline=False,
                )
                await interaction.followup.send(embed=embed)

                # Use centralized turn announcement for Round 1
                await self._announce_turn(interaction.channel_id, match_state)
        except Exception as e:
            logger.error(f"Error in start_match: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while starting the match.", ephemeral=True
            )

    @app_commands.command(
        name="pick",
        description="Pick a player for the current match round (shows dropdown menu)",
    )
    async def select_player(self, interaction: discord.Interaction):
        """Show player pick dropdown menu"""
        await interaction.response.defer(ephemeral=True)

        # Check if there's an active match
        match_state = await self._get_match_state(interaction.channel_id)
        if not match_state:
            await interaction.followup.send(
                "❌ No active match in this channel!", ephemeral=True
            )
            return

        # Check if it's this user's turn
        if match_state.current_turn != interaction.user.id:
            await interaction.followup.send("❌ It's not your turn!", ephemeral=True)
            return

        # Send pick menu (duplicate prevention handled inside)
        await self._send_player_pick_menu(interaction.channel_id, interaction.user.id)

        await interaction.followup.send(
            "✅ Check your DMs for the pick menu!", ephemeral=True
        )

    async def _complete_match(
        self,
        interaction: discord.Interaction,
        match_state: MatchState,
        match_channel=None,
    ):
        """_complete_match"""
        # Note: This is a helper function called from within a command that already deferred
        # Do not defer here as the interaction was already handled

        try:
            async with AsyncSessionLocal() as session:
                # Get users
                player1 = await self.bot.fetch_user(match_state.player1_id)
                player2 = await self.bot.fetch_user(match_state.player2_id)

                # Create match record
                winner_id = match_state.get_winner()

                # CRITICAL: Log final scores for debugging
                logger.info(
                    f"Match complete! Player 1 ({player1.name}): {match_state.player1_score}, Player 2 ({player2.name}): {match_state.player2_score}"
                )
                logger.info(
                    f"Winner ID: {winner_id}, Player 1 ID: {match_state.player1_id}, Player 2 ID: {match_state.player2_id}"
                )
                logger.info(f"Round history: {len(match_state.round_history)} rounds")

                # Log round-by-round details with card IDs for verification
                for i, round_data in enumerate(match_state.round_history, 1):
                    p1_card = round_data.get("player1_card", "N/A")
                    p1_card_id = round_data.get("player1_card_id", "N/A")
                    p2_card = round_data.get("player2_card", "N/A")
                    p2_card_id = round_data.get("player2_card_id", "N/A")
                    winner_id_round = round_data.get("winner_id", "N/A")
                    logger.info(
                        f"Round {i}: Score={round_data.get('score', 'N/A')}, P1={p1_card} (ID: {p1_card_id}), P2={p2_card} (ID: {p2_card_id}), Winner={winner_id_round}"
                    )

                # Log round winners summary
                if hasattr(match_state, "round_winners"):
                    p1_wins = sum(
                        1
                        for w in match_state.round_winners
                        if w == match_state.player1_id
                    )
                    p2_wins = sum(
                        1
                        for w in match_state.round_winners
                        if w == match_state.player2_id
                    )
                    draws = sum(1 for w in match_state.round_winners if w is None)
                    logger.info(
                        f"Round winners summary: Player 1 wins={p1_wins}, Player 2 wins={p2_wins}, Draws={draws}"
                    )

                # Get guild_id from match_channel if available, otherwise from interaction
                guild_id = (
                    match_channel.guild.id if match_channel else interaction.guild.id
                )

                match_record = Match(
                    guild_id=guild_id,
                    player1_id=match_state.player1_id,
                    player2_id=match_state.player2_id,
                    player1_score=match_state.player1_score,
                    player2_score=match_state.player2_score,
                    winner_id=winner_id,
                    match_details=json.dumps([r for r in match_state.round_history]),
                    completed_at=discord.utils.utcnow(),
                )
                session.add(match_record)

                # Update user stats - ensure users exist
                result = await session.execute(
                    select(User).where(
                        User.id.in_([match_state.player1_id, match_state.player2_id])
                    )
                )
                users = result.scalars().all()
                user_dict = {user.id: user for user in users}

                # Create missing users
                for user_id, player in [
                    (match_state.player1_id, player1),
                    (match_state.player2_id, player2),
                ]:
                    if user_id not in user_dict:
                        logger.warning(
                            f"Creating missing user {user_id} ({player.name}) during match completion"
                        )
                        new_user = User(
                            id=user_id,
                            username=player.name,
                            total_games=0,
                            total_wins=0,
                            total_draws=0,
                            total_losses=0,
                        )
                        session.add(new_user)
                        await session.flush()
                        user_dict[user_id] = new_user

                # Update stats for both users
                for user_id in [match_state.player1_id, match_state.player2_id]:
                    user = user_dict[user_id]
                    user.total_games += 1
                    if winner_id == user.id:
                        user.total_wins += 1
                    elif winner_id is None:
                        user.total_draws += 1
                    else:
                        user.total_losses += 1

                # Update leaderboard
                await self._update_leaderboard(
                    session,
                    guild_id,
                    match_state.player1_id,
                    won=(winner_id == match_state.player1_id),
                    draw=(winner_id is None),
                )
                await self._update_leaderboard(
                    session,
                    guild_id,
                    match_state.player2_id,
                    won=(winner_id == match_state.player2_id),
                    draw=(winner_id is None),
                )

                # Remove active match - handle multiple matches if they exist
                channel_id = (
                    match_channel.id if match_channel else interaction.channel_id
                )
                result = await session.execute(
                    select(ActiveMatch).where(ActiveMatch.channel_id == channel_id)
                )
                active_matches = result.scalars().all()
                for active in active_matches:
                    await session.delete(active)

                # Process any active bets BEFORE committing
                bet_results = await self._process_bets(
                    session,
                    guild_id,
                    match_state.player1_id,
                    match_state.player2_id,
                    winner_id,
                )

                await session.commit()

            # Show match complete embed
            embed = EmbedBuilder.match_complete_embed(
                match_state, player1.name, player2.name
            )
            # Send to match channel if available, otherwise to interaction channel
            target_channel = match_channel if match_channel else interaction.channel
            await target_channel.send(embed=embed)

            # Send bet notifications to users
            if bet_results:
                await self._send_bet_notifications(bet_results, winner_id)
                # Also send public notification in match channel
                await self._send_public_bet_results(
                    target_channel, bet_results, winner_id, player1, player2
                )

            # Remove from Redis and active matches
            channel_id = match_channel.id if match_channel else interaction.channel_id
            await self._delete_match_state(channel_id)
        except Exception as e:
            logger.error(f"Error in _complete_match: {e}", exc_info=True)
            # Try to send error message
            try:
                await interaction.channel.send(
                    "❌ An error occurred while completing the match.",
                )
            except:
                pass

    async def _process_bets(
        self,
        session: AsyncSession,
        guild_id: int,
        player1_id: int,
        player2_id: int,
        winner_id: Optional[int],
    ) -> list[dict]:
        """Process bets for completed match - winner gets ALL cards from both sides

        Returns:
            List of dicts with bet results for notification
        """
        bet_results = []

        # Fetch all bets for this match
        result = await session.execute(
            select(Bet)
            .where(Bet.guild_id == guild_id)
            .where(Bet.accepted == True)
            .where(Bet.completed == False)
            .where(
                ((Bet.creator_id == player1_id) & (Bet.challenged_id == player2_id))
                | ((Bet.creator_id == player2_id) & (Bet.challenged_id == player1_id))
            )
        )
        bets = result.scalars().all()

        logger.info(
            f"[BET] Found {len(bets)} bets for match {player1_id} vs {player2_id}, winner={winner_id}"
        )

        for bet in bets:
            logger.info(
                f"[BET] Processing bet {bet.id} - Creator: {bet.creator_id}, Challenged: {bet.challenged_id}"
            )
            logger.info(
                f"[BET] Creator cards: {bet.creator_cards}, Challenged cards: {bet.challenged_cards}"
            )

            # If draw → nothing transferred
            if winner_id is None:
                logger.info(f"[BET] Draw → no card transfers for bet {bet.id}")
                bet.completed = True
                continue

            # Determine winner and loser
            if winner_id == bet.creator_id:
                loser_id = bet.challenged_id
                loser_cards = bet.challenged_cards or []
                winner_cards = bet.creator_cards or []
                real_winner = bet.creator_id
            else:
                loser_id = bet.creator_id
                loser_cards = bet.creator_cards or []
                winner_cards = bet.challenged_cards or []
                real_winner = bet.challenged_id

            logger.info(f"[BET] Winner={real_winner}, Loser={loser_id}")
            logger.info(
                f"[BET] Winner's bet cards: {winner_cards}, Loser's bet cards: {loser_cards}"
            )

            # Transfer loser's cards to winner
            for card_id in loser_cards:
                # 1. Remove card from loser
                del_result = await session.execute(
                    select(Collection)
                    .where(Collection.user_id == loser_id)
                    .where(Collection.card_id == card_id)
                )
                loser_entries = del_result.scalars().all()

                if loser_entries:
                    for entry in loser_entries:
                        await session.delete(entry)
                    logger.info(
                        f"[BET] Removed card {card_id} from loser {loser_id} ({len(loser_entries)} copies removed)"
                    )
                else:
                    logger.warning(
                        f"[BET] Loser {loser_id} had no copy of card {card_id} — continuing anyway"
                    )

                # 2. Add card to winner (if they don't already have it)
                exists_result = await session.execute(
                    select(Collection)
                    .where(Collection.user_id == real_winner)
                    .where(Collection.card_id == card_id)
                )
                existing = exists_result.scalars().first()

                if existing:
                    logger.info(
                        f"[BET] Winner {real_winner} already owns card {card_id}, skipping insert"
                    )
                else:
                    new_collection = Collection(user_id=real_winner, card_id=card_id)
                    session.add(new_collection)
                    logger.info(
                        f"[BET] Transferred card {card_id} from loser to winner {real_winner}"
                    )

            # Ensure winner keeps their own bet cards (they should already have them, but verify)
            for card_id in winner_cards:
                exists_result = await session.execute(
                    select(Collection)
                    .where(Collection.user_id == real_winner)
                    .where(Collection.card_id == card_id)
                )
                existing = exists_result.scalars().first()

                if not existing:
                    # Winner should have their cards, but if missing, add them back
                    logger.warning(
                        f"[BET] Winner {real_winner} missing their bet card {card_id}, restoring it"
                    )
                    new_collection = Collection(user_id=real_winner, card_id=card_id)
                    session.add(new_collection)
                else:
                    logger.info(
                        f"[BET] Winner {real_winner} keeps their bet card {card_id}"
                    )

            bet.completed = True
            bet.winner_id = real_winner

            logger.info(
                f"[BET] Bet {bet.id} completed - Winner {real_winner} gets all {len(loser_cards) + len(winner_cards)} cards"
            )

            # Store bet result for notification
            bet_results.append(
                {
                    "bet_id": bet.id,
                    "winner_id": real_winner,
                    "loser_id": loser_id,
                    "winner_cards_won": loser_cards,
                    "total_cards": len(loser_cards) + len(winner_cards),
                    "creator_id": bet.creator_id,
                    "challenged_id": bet.challenged_id,
                }
            )

        # CRITICAL: Write everything to DB immediately.
        await session.flush()
        await session.commit()
        logger.info(f"[BET] All {len(bets)} bets processed + committed")

        return bet_results

    async def _send_bet_notifications(
        self, bet_results: list[dict], winner_id: Optional[int]
    ):
        """Send DM notifications to users about bet results"""
        for result in bet_results:
            winner = self.bot.get_user(result["winner_id"])
            loser = self.bot.get_user(result["loser_id"])

            if winner_id is None:
                # Draw - notify both users
                draw_embed = discord.Embed(
                    title="🤝 Bet Draw",
                    description="Your bet ended in a draw! All cards have been returned.",
                    color=discord.Color.blue(),
                )

                if winner:
                    try:
                        await winner.send(embed=draw_embed)
                    except Exception as e:
                        logger.warning(f"Could not DM user {result['winner_id']}: {e}")

                if loser:
                    try:
                        await loser.send(embed=draw_embed)
                    except Exception as e:
                        logger.warning(f"Could not DM user {result['loser_id']}: {e}")
            else:
                # Winner notification
                if winner:
                    winner_embed = discord.Embed(
                        title="🎉 Bet Won!",
                        description=f"Congratulations! You won your bet!",
                        color=discord.Color.green(),
                    )
                    winner_embed.add_field(
                        name="Cards Won",
                        value=f"{len(result['winner_cards_won'])} cards from your opponent",
                        inline=False,
                    )
                    winner_embed.add_field(
                        name="Total Cards",
                        value=f"You now have all {result['total_cards']} cards from the bet!",
                        inline=False,
                    )

                    try:
                        await winner.send(embed=winner_embed)
                    except Exception as e:
                        logger.warning(
                            f"Could not DM winner {result['winner_id']}: {e}"
                        )

                # Loser notification
                if loser:
                    loser_embed = discord.Embed(
                        title="😔 Bet Lost",
                        description=f"Unfortunately, you lost your bet.",
                        color=discord.Color.red(),
                    )
                    loser_embed.add_field(
                        name="Cards Lost",
                        value=f"{len(result['winner_cards_won'])} cards transferred to the winner",
                        inline=False,
                    )
                    loser_embed.add_field(
                        name="Better Luck Next Time!",
                        value="Keep playing to rebuild your collection!",
                        inline=False,
                    )

                    try:
                        await loser.send(embed=loser_embed)
                    except Exception as e:
                        logger.warning(f"Could not DM loser {result['loser_id']}: {e}")

    async def _send_public_bet_results(
        self,
        channel: discord.TextChannel,
        bet_results: list[dict],
        winner_id: Optional[int],
        player1: discord.Member,
        player2: discord.Member,
    ):
        """Send public bet results notification in match channel"""
        if not bet_results:
            return

        embed = discord.Embed(
            title="🎲 Bet Results",
            color=discord.Color.gold() if winner_id else discord.Color.blue(),
        )

        if winner_id is None:
            embed.description = (
                f"**Draw!** All {len(bet_results)} bet(s) ended in a draw.\n"
                f"All cards have been returned to their original owners."
            )
        else:
            winner_user = player1 if winner_id == player1.id else player2
            loser_user = player2 if winner_id == player1.id else player1

            total_cards_won = sum(len(r["winner_cards_won"]) for r in bet_results)

            embed.description = (
                f"🎉 {winner_user.mention} won {len(bet_results)} bet(s)!\n"
                f"💰 **{total_cards_won}** cards transferred from {loser_user.mention}!"
            )

            for i, result in enumerate(bet_results, 1):
                embed.add_field(
                    name=f"Bet #{i}",
                    value=f"**{len(result['winner_cards_won'])}** cards won\n"
                    f"Total: {result['total_cards']} cards",
                    inline=True,
                )

        embed.set_footer(text="Check your DMs for detailed bet results!")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"Could not send public bet results to channel: {e}")

    @app_commands.command(name="bet", description="Bet cards against another user")
    @app_commands.describe(
        opponent="The user you want to bet against",
        card_name="Name of card to bet (use command multiple times for multiple cards)",
    )
    async def create_bet(
        self, interaction: discord.Interaction, opponent: discord.Member, card_name: str
    ):
        """Create or add to a bet"""
        # Defer immediately to avoid interaction timeout
        await interaction.response.defer(ephemeral=False)

        # Early validation
        if opponent.bot or opponent.id == interaction.user.id:
            await interaction.followup.send(
                "❌ You can't bet against bots or yourself!", ephemeral=True
            )
            return

        try:
            async with AsyncSessionLocal() as session:
                # Check if user is already in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, interaction.user.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ You cannot create or modify bets while in an active match!\n"
                        f"Please complete your match in <#{channel_id}> first.",
                        ephemeral=True,
                    )
                    return

                # Check if opponent is already in an active match
                is_in_match, channel_id = await is_user_in_active_match(
                    session, opponent.id
                )
                if is_in_match:
                    await interaction.followup.send(
                        f"⚠️ {opponent.mention} is already in an active match in <#{channel_id}>!\n"
                        f"You cannot bet with them until their match is complete.",
                        ephemeral=True,
                    )
                    return

                # Find card in collection
                result = await session.execute(
                    select(Card, Collection)
                    .join(Collection, Card.id == Collection.card_id)
                    .where(Collection.user_id == interaction.user.id)
                    .where(Card.name.ilike(f"%{card_name}%"))
                )
                card_data = result.first()

                if not card_data:
                    await interaction.followup.send(
                        f"❌ You don't have a card matching '{card_name}'!",
                        ephemeral=True,
                    )
                    return

                card, _ = card_data

                # Check if card is currently in user's team lineup
                result = await session.execute(
                    select(TeamSlot)
                    .join(Team, TeamSlot.team_id == Team.id)
                    .where(Team.user_id == interaction.user.id)
                    .where(Team.guild_id == interaction.guild.id)
                    .where(TeamSlot.card_id == card.id)
                )
                team_slot = result.scalar_one_or_none()

                if team_slot:
                    await interaction.followup.send(
                        f"❌ **{card.name}** is currently in your team lineup!\n"
                        f"You cannot bet cards that are in your active team. Remove it from your team first.",
                        ephemeral=True,
                    )
                    return

                # Check for existing bet where user is creator
                result = await session.execute(
                    select(Bet)
                    .where(Bet.guild_id == interaction.guild.id)
                    .where(Bet.creator_id == interaction.user.id)
                    .where(Bet.challenged_id == opponent.id)
                    .where(Bet.accepted == False)
                )
                existing_bet_as_creator = result.scalar_one_or_none()

                # Check for existing bet where user is challenged (accepting a bet)
                result = await session.execute(
                    select(Bet)
                    .where(Bet.guild_id == interaction.guild.id)
                    .where(Bet.creator_id == opponent.id)
                    .where(Bet.challenged_id == interaction.user.id)
                    .where(Bet.accepted == False)
                )
                existing_bet_as_challenged = result.scalar_one_or_none()

                if existing_bet_as_creator:
                    # User is creator, adding more cards to their bet
                    if len(existing_bet_as_creator.creator_cards) >= 3:
                        await interaction.followup.send(
                            "❌ You can only bet up to 3 cards!", ephemeral=True
                        )
                        return

                    # Check if card is already in this bet
                    if card.id in existing_bet_as_creator.creator_cards:
                        await interaction.followup.send(
                            f"❌ **{card.name}** is already in your bet!",
                            ephemeral=True,
                        )
                        return

                    # Verify user still owns the card
                    verify_result = await session.execute(
                        select(Collection)
                        .where(Collection.user_id == interaction.user.id)
                        .where(Collection.card_id == card.id)
                    )
                    if not verify_result.scalars().first():
                        await interaction.followup.send(
                            f"❌ You no longer own **{card.name}**!",
                            ephemeral=True,
                        )
                        return

                    existing_bet_as_creator.creator_cards.append(card.id)
                    await session.commit()

                    await interaction.followup.send(
                        f"✅ Added **{card.name}** to your bet against {opponent.mention}!",
                        ephemeral=True,
                    )
                elif existing_bet_as_challenged:
                    # User is challenged, accepting the bet by adding their cards
                    if len(existing_bet_as_challenged.challenged_cards) >= 3:
                        await interaction.followup.send(
                            "❌ You can only bet up to 3 cards!", ephemeral=True
                        )
                        return

                    # Check if card is already in this bet
                    if card.id in existing_bet_as_challenged.challenged_cards:
                        await interaction.followup.send(
                            f"❌ **{card.name}** is already in your bet!",
                            ephemeral=True,
                        )
                        return

                    # Verify user still owns the card
                    verify_result = await session.execute(
                        select(Collection)
                        .where(Collection.user_id == interaction.user.id)
                        .where(Collection.card_id == card.id)
                    )
                    if not verify_result.scalars().first():
                        await interaction.followup.send(
                            f"❌ You no longer own **{card.name}**!",
                            ephemeral=True,
                        )
                        return

                    existing_bet_as_challenged.challenged_cards.append(card.id)

                    # Check if both players have matched number of cards
                    if len(existing_bet_as_challenged.challenged_cards) == len(
                        existing_bet_as_challenged.creator_cards
                    ):
                        existing_bet_as_challenged.accepted = True
                        await interaction.followup.send(
                            f"✅ Bet accepted! You matched with **{card.name}**.\n"
                            f"🎲 The bet is now active! Winner takes all cards.",
                            ephemeral=False,
                        )
                    else:
                        await interaction.followup.send(
                            f"✅ Added **{card.name}** to your bet!\n"
                            f"Match {len(existing_bet_as_challenged.creator_cards)} cards to accept the bet.",
                            ephemeral=False,
                        )

                    await session.commit()
                else:
                    # Verify user still owns the card before creating bet
                    verify_result = await session.execute(
                        select(Collection)
                        .where(Collection.user_id == interaction.user.id)
                        .where(Collection.card_id == card.id)
                    )
                    if not verify_result.scalars().first():
                        await interaction.followup.send(
                            f"❌ You no longer own **{card.name}**!",
                            ephemeral=True,
                        )
                        return

                    # Create new bet
                    new_bet = Bet(
                        guild_id=interaction.guild.id,
                        creator_id=interaction.user.id,
                        challenged_id=opponent.id,
                        creator_cards=[card.id],
                        challenged_cards=[],
                    )
                    session.add(new_bet)
                    await session.commit()

                    embed = discord.Embed(
                        title="🎲 New Bet Created!",
                        description=f"{interaction.user.mention} has challenged {opponent.mention} to a bet!",
                        color=discord.Color.gold(),
                    )
                    embed.add_field(
                        name="Wagered Card", value=f"**{card.name}**", inline=False
                    )
                    embed.add_field(
                        name="To Accept",
                        value=f"{opponent.mention}, use `/bet {interaction.user.mention} <card_name>` to match the bet!",
                        inline=False,
                    )

                    await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in create_bet: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while creating the bet.", ephemeral=True
            )

    @app_commands.command(name="leaderboard", description="View the server leaderboard")
    async def view_leaderboard(self, interaction: discord.Interaction):
        """view_leaderboard"""
        await interaction.response.defer(ephemeral=False)

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Leaderboard, User)
                    .join(User, Leaderboard.user_id == User.id)
                    .where(Leaderboard.guild_id == interaction.guild.id)
                    .order_by(Leaderboard.points.desc())
                )
                entries = result.all()

                embed = EmbedBuilder.leaderboard_embed(
                    interaction.guild.name, [(user, lb) for lb, user in entries]
                )

                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging

            logger = logging.getLogger("discord_bot")
            logger.error(f"Error in view_leaderboard: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching the leaderboard.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(MatchCog(bot))
