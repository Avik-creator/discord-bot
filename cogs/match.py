import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.database import AsyncSessionLocal
from database.models import User, Team, TeamSlot, Card, Match, ActiveMatch, Bet, Leaderboard, Collection
from utils.embeds import EmbedBuilder
from utils.match_engine import MatchEngine, MatchState
from typing import Dict, Optional
import json
import logging

logger = logging.getLogger('discord_bot')

class PlayerSelectView(discord.ui.View):
    """View with select menu for picking players"""
    
    def __init__(self, match_state: MatchState, user_id: int, cog_instance):
        super().__init__(timeout=300)  # 5 minute timeout
        self.match_state = match_state
        self.user_id = user_id
        self.cog = cog_instance
        
        # Validate user_id is one of the players
        if user_id != match_state.player1_id and user_id != match_state.player2_id:
            logger.error(f"PlayerSelectView: Invalid user_id {user_id}. Player1: {match_state.player1_id}, Player2: {match_state.player2_id}")
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
        logger.info(f"Building dropdown for user {user_id}, round {match_state.current_round}. Available: {len(available_cards)} cards")
        if user_id == match_state.player1_id:
            logger.info(f"Player 1 used positions: {match_state.player1_used_cards}, used card IDs: {match_state.player1_used_card_ids}")
        else:
            logger.info(f"Player 2 used positions: {match_state.player2_used_cards}, used card IDs: {match_state.player2_used_card_ids}")
        
        options = []
        for position, card in available_cards.items():
            # Double-check the card hasn't been used (defensive programming)
            if position in used_positions:
                logger.error(f"CRITICAL: Position {position} found in available_cards but also in used_positions for user {user_id}. Skipping!")
                continue
            
            if card.id in used_card_ids:
                logger.error(f"CRITICAL: Card {card.name} (ID: {card.id}) found in available_cards but also in used_card_ids for user {user_id}. Skipping!")
                continue
            
            # This card is available - add to dropdown
            label = card.name[:100]  # Discord limit is 100 chars
            description = f"{position} - {card.attack_stat} ATK / {card.defense_stat} DEF"[:100]
            options.append(discord.SelectOption(
                label=label,
                description=description,
                value=position
            ))
        
        if options:
            select = discord.ui.Select(
                placeholder="Choose a player...",
                options=options[:25]  # Discord limit is 25 options
            )
            select.callback = self.on_select
            self.add_item(select)
        else:
            # No available cards - this shouldn't happen, but handle it
            select = discord.ui.Select(
                placeholder="No players available!",
                options=[discord.SelectOption(label="No players", value="none", description="All players used")]
            )
            select.callback = self.on_select
            self.add_item(select)
    
    async def on_select(self, interaction: discord.Interaction):
        """Handle player selection"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ This menu is not for you!",
                ephemeral=True
            )
            return
        
        if interaction.channel_id not in self.cog.active_matches:
            await interaction.response.send_message(
                "❌ No active match in this channel!",
                ephemeral=True
            )
            return
        
        # Verify it's still this user's turn
        if self.match_state.current_turn != self.user_id:
            await interaction.response.send_message(
                "❌ It's not your turn anymore!",
                ephemeral=True
            )
            return
        
        selected_position = interaction.data['values'][0]
        
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
            await interaction.response.send_message(
                f"❌ Position {selected_position} is not in your team!",
                ephemeral=True
            )
            return
        
        # Get the card from the team
        selected_card = team[selected_position]
        
        # Verify the card hasn't been used
        if selected_position in used_positions:
            await interaction.response.send_message(
                "❌ This position has already been used in this match!",
                ephemeral=True
            )
            return
        
        if selected_card.id in used_card_ids:
            await interaction.response.send_message(
                f"❌ **{selected_card.name}** has already been used in this match!",
                ephemeral=True
            )
            return
        
        # Mark card as selected
        if not self.match_state.select_card(self.user_id, selected_position):
            await interaction.response.send_message(
                "❌ Failed to select this card. It may have already been used!",
                ephemeral=True
            )
            return
        
        # CRITICAL: Verify the card was actually marked as used
        if self.user_id == self.match_state.player1_id:
            if selected_position not in self.match_state.player1_used_cards:
                logger.error(f"CRITICAL BUG: Position {selected_position} was not added to player1_used_cards after select_card!")
            if selected_card.id not in self.match_state.player1_used_card_ids:
                logger.error(f"CRITICAL BUG: Card {selected_card.name} (ID: {selected_card.id}) was not added to player1_used_card_ids after select_card!")
        else:
            if selected_position not in self.match_state.player2_used_cards:
                logger.error(f"CRITICAL BUG: Position {selected_position} was not added to player2_used_cards after select_card!")
            if selected_card.id not in self.match_state.player2_used_card_ids:
                logger.error(f"CRITICAL BUG: Card {selected_card.name} (ID: {selected_card.id}) was not added to player2_used_card_ids after select_card!")
        
        # Log the selection for debugging
        logger.info(f"Player {self.user_id} selected card {selected_card.name} (ID: {selected_card.id}) at position {selected_position} in round {self.match_state.current_round}")
        logger.info(f"Player {self.user_id} used positions: {self.match_state.player1_used_cards if self.user_id == self.match_state.player1_id else self.match_state.player2_used_cards}")
        logger.info(f"Player {self.user_id} used card IDs: {self.match_state.player1_used_card_ids if self.user_id == self.match_state.player1_id else self.match_state.player2_used_card_ids}")
        
        # Handle the selection (similar to the old pick command logic)
        await interaction.response.defer(ephemeral=True)
        
        # Use the selected_card from team to ensure we have the correct card name
        selected_card_name = selected_card.name
        
        # Check if both players have selected
        if self.user_id == self.match_state.player1_id:
            # Player 1 selected - switch turn to player 2
            self.match_state.current_turn = self.match_state.player2_id
            # Player 1 selected, now wait for player 2
            await interaction.followup.send(
                f"✅ You selected **{selected_card_name}** ({selected_position})!\n"
                f"Waiting for <@{self.match_state.player2_id}>...",
                ephemeral=True
            )
            
            # Notify player 2 with dropdown
            await self.cog._send_player_pick_menu(interaction.channel, self.match_state, self.match_state.player2_id)
        else:
            # Player 2 selected, now play the round
            # Get both selected positions
            player1_used = list(self.match_state.player1_used_cards)
            player2_used = list(self.match_state.player2_used_cards)
            
            player1_position = player1_used[-1]
            player2_position = selected_position
            
            # Play round
            round_data = self.match_state.play_round(player1_position, player2_position)
            
            # Show round result
            player1 = await self.cog.bot.fetch_user(self.match_state.player1_id)
            player2 = await self.cog.bot.fetch_user(self.match_state.player2_id)
            
            embed = EmbedBuilder.match_round_embed(
                round_data,
                player1.name,
                player2.name
            )
            
            await interaction.followup.send(embed=embed)
            
            # Check if match is complete
            if self.match_state.is_complete():
                await self.cog._complete_match(interaction, self.match_state)
            else:
                # Next round - send pick menu to next player
                await self.cog._send_player_pick_menu(interaction.channel, self.match_state, self.match_state.current_turn)

class MatchCog(commands.Cog):
    """Match and betting commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_matches = {}  # {channel_id: MatchState}
        self.last_dropdown_sent = {}  # {channel_id: (round, user_id)} - Track last dropdown sent to prevent duplicates
    
    async def _send_player_pick_menu(self, channel, match_state: MatchState, user_id: int):
        """Send a message with player pick dropdown menu - only usable by the specified user"""
        try:
            # Validate user_id is one of the players
            if user_id != match_state.player1_id and user_id != match_state.player2_id:
                logger.error(f"Invalid user_id {user_id} passed to _send_player_pick_menu. Player1: {match_state.player1_id}, Player2: {match_state.player2_id}")
                return
            
            # Validate it's the correct user's turn - CRITICAL: Only send to current player
            if match_state.current_turn != user_id:
                logger.error(f"ERROR: Attempted to send pick menu to user {user_id} but current_turn is {match_state.current_turn}. Aborting to prevent showing wrong team!")
                return
            
            # CRITICAL: Prevent duplicate dropdowns - check if we already sent one for this round
            channel_key = channel.id
            last_sent = self.last_dropdown_sent.get(channel_key)
            if last_sent and last_sent[0] == match_state.current_round:
                logger.error(f"DUPLICATE DROPDOWN PREVENTED: Already sent dropdown for round {match_state.current_round} to user {last_sent[1]}. Attempted to send to user {user_id}. Aborting!")
                return
            
            # Track that we're sending this dropdown
            self.last_dropdown_sent[channel_key] = (match_state.current_round, user_id)
            logger.info(f"Sending pick menu to user {user_id} for round {match_state.current_round}")
            
            user = await self.bot.fetch_user(user_id)
            
            # Use get_available_cards to ensure consistency with dropdown building
            available_cards = match_state.get_available_cards(user_id)
            
            # Log for debugging
            logger.info(f"Sending pick menu to user {user_id} (name: {user.name}) for round {match_state.current_round}. Available cards: {len(available_cards)}")
            if user_id == match_state.player1_id:
                logger.info(f"Player 1 used positions: {match_state.player1_used_cards}, used card IDs: {match_state.player1_used_card_ids}")
            else:
                logger.info(f"Player 2 used positions: {match_state.player2_used_cards}, used card IDs: {match_state.player2_used_card_ids}")
            
            embed = discord.Embed(
                title=f"⚽ {user.display_name}'s Turn!",
                description=f"**Round {match_state.current_round}** - <@{user_id}>, select a player from the dropdown below!\n\n"
                          f"⚠️ **Only {user.display_name} can use this dropdown.**",
                color=discord.Color.blue()
            )
            
            # Add available players info with stats
            player_list = []
            for pos, card in list(available_cards.items())[:15]:  # Show more players
                player_list.append(f"**{card.name}** ({pos}) - {card.attack_stat} ATK / {card.defense_stat} DEF")
            
            if len(available_cards) > 15:
                player_list.append(f"\n... and {len(available_cards) - 15} more players available")
            
            embed.add_field(
                name=f"📋 Available Players ({len(available_cards)} remaining)",
                value="\n".join(player_list) if player_list else "No players available",
                inline=False
            )
            
            embed.set_footer(text=f"Only {user.display_name} can use the dropdown below")
            
            # Create view with validated user_id
            view = PlayerSelectView(match_state, user_id, self)
            
            # Log for debugging
            logger.info(f"Sending pick menu to user {user_id} (name: {user.name}) for match in channel {channel.id}. Current turn: {match_state.current_turn}")
            
            await channel.send(f"<@{user_id}>", embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error sending player pick menu: {e}", exc_info=True)
    
    async def _get_team_data(self, session: AsyncSession, user_id: int) -> tuple[Optional[Team], Dict]:
        """Get team and slots for a user"""
        result = await session.execute(
            select(Team).where(Team.user_id == user_id)
        )
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
            logger.warning(f"Team {team.id} for user {user_id} has only {len(team_slots)} players, need 11")
            return team, {}
        
        return team, team_slots
    
    async def _update_leaderboard(self, session: AsyncSession, guild_id: int, 
                                  user_id: int, won: bool, draw: bool):
        """Update leaderboard entry for a user"""
        result = await session.execute(
            select(Leaderboard)
            .where(Leaderboard.guild_id == guild_id)
            .where(Leaderboard.user_id == user_id)
        )
        lb_entry = result.scalar_one_or_none()
        
        if not lb_entry:
            lb_entry = Leaderboard(
                guild_id=guild_id,
                user_id=user_id,
                points=0,
                wins=0,
                draws=0,
                losses=0
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
    
    @app_commands.command(name="match", description="Start a match against another user")
    @app_commands.describe(opponent="The user you want to challenge")
    async def start_match(self, interaction: discord.Interaction, opponent: discord.Member):
        """Start a match against another user"""
        # Defer immediately to avoid interaction timeout
        await interaction.response.defer(ephemeral=False)
        
        # Early validation
        if opponent.bot or opponent.id == interaction.user.id:
            await interaction.followup.send(
                "❌ You can't challenge bots or yourself!",
                ephemeral=True
            )
            return
        
        # Check if there's already an active match in this channel
        if interaction.channel_id in self.active_matches:
            await interaction.followup.send(
                "❌ There's already an active match in this channel!",
                ephemeral=True
            )
            return
        
        try:
            async with AsyncSessionLocal() as session:
                # Get both teams
                player1_team, player1_slots = await self._get_team_data(session, interaction.user.id)
                player2_team, player2_slots = await self._get_team_data(session, opponent.id)
                
                if not player1_team or not player1_slots:
                    await interaction.followup.send(
                        "❌ You need a complete team with 11 players to play!",
                        ephemeral=True
                    )
                    return
                
                if not player2_team or not player2_slots:
                    await interaction.followup.send(
                        f"❌ {opponent.mention} needs a complete team with 11 players to play!",
                        ephemeral=True
                    )
                    return
                
                # Create match state
                match_state = MatchState(
                    player1_id=interaction.user.id,
                    player2_id=opponent.id,
                    player1_team=player1_slots,
                    player2_team=player2_slots,
                    player1_formation=player1_team.formation,
                    player2_formation=player2_team.formation
                )
                
                # Store in active matches
                self.active_matches[interaction.channel_id] = match_state
                
                # Create active match record in database
                active_match = ActiveMatch(
                    guild_id=interaction.guild.id,
                    channel_id=interaction.channel_id,
                    player1_id=interaction.user.id,
                    player2_id=opponent.id,
                    current_round=1,
                    current_turn_player=interaction.user.id,
                    game_state={}
                )
                session.add(active_match)
                await session.commit()
                
                # Create match announcement
                embed = discord.Embed(
                    title="⚽ Match Started!",
                    description=f"{interaction.user.mention} vs {opponent.mention}",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="How to Play",
                    value="Each player selects a card for 11 rounds.\n"
                          "Odd rounds: Player 1 attacks\n"
                          "Even rounds: Player 2 attacks\n"
                          "Attack stat vs Defense stat wins the round!",
                    inline=False
                )
                
                # Show available players for both players
                player1_cards = match_state.get_available_cards(interaction.user.id)
                player2_cards = match_state.get_available_cards(opponent.id)
                
                p1_list = [f"**{card.name}** ({pos})" for pos, card in list(player1_cards.items())[:8]]
                if len(player1_cards) > 8:
                    p1_list.append(f"... and {len(player1_cards) - 8} more")
                
                p2_list = [f"**{card.name}** ({pos})" for pos, card in list(player2_cards.items())[:8]]
                if len(player2_cards) > 8:
                    p2_list.append(f"... and {len(player2_cards) - 8} more")
                
                embed.add_field(
                    name=f"👤 {interaction.user.display_name}'s Team ({len(player1_cards)} players)",
                    value="\n".join(p1_list) if p1_list else "No players",
                    inline=True
                )
                embed.add_field(
                    name=f"👤 {opponent.display_name}'s Team ({len(player2_cards)} players)",
                    value="\n".join(p2_list) if p2_list else "No players",
                    inline=True
                )
                
                embed.add_field(
                    name="Current Turn",
                    value=f"{interaction.user.mention} - Select a player from the dropdown below!",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed)
                
                # Send player pick menu
                await self._send_player_pick_menu(interaction.channel, match_state, interaction.user.id)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in start_match: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while starting the match.",
                ephemeral=True
            )
    
    @app_commands.command(name="pick", description="Pick a player for the current match round (shows dropdown menu)")
    async def select_player(self, interaction: discord.Interaction):
        """Show player pick dropdown menu"""
        # Defer immediately to avoid interaction timeout
        await interaction.response.defer(ephemeral=True)
        
        # Check if there's an active match
        if interaction.channel_id not in self.active_matches:
            await interaction.followup.send(
                "❌ No active match in this channel!",
                ephemeral=True
            )
            return
        
        match_state = self.active_matches[interaction.channel_id]
        
        # Check if it's this user's turn
        if match_state.current_turn != interaction.user.id:
            await interaction.followup.send(
                "❌ It's not your turn!",
                ephemeral=True
            )
            return
        
        # Get available cards
        available_cards = match_state.get_available_cards(interaction.user.id)
        
        if not available_cards:
            await interaction.followup.send(
                "❌ No available players!",
                ephemeral=True
            )
            return
        
        # Create and send pick menu
        embed = discord.Embed(
            title="⚽ Select Your Player",
            description=f"Choose a player for Round {match_state.current_round}",
            color=discord.Color.blue()
        )
        
        view = PlayerSelectView(match_state, interaction.user.id, self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def _complete_match(self, interaction: discord.Interaction, match_state: MatchState):
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
                logger.info(f"Match complete! Player 1 ({player1.name}): {match_state.player1_score}, Player 2 ({player2.name}): {match_state.player2_score}")
                logger.info(f"Winner ID: {winner_id}, Player 1 ID: {match_state.player1_id}, Player 2 ID: {match_state.player2_id}")
                logger.info(f"Round history: {len(match_state.round_history)} rounds")
                
                # Log round-by-round details with card IDs for verification
                for i, round_data in enumerate(match_state.round_history, 1):
                    p1_card = round_data.get('player1_card', 'N/A')
                    p1_card_id = round_data.get('player1_card_id', 'N/A')
                    p2_card = round_data.get('player2_card', 'N/A')
                    p2_card_id = round_data.get('player2_card_id', 'N/A')
                    winner_id_round = round_data.get('winner_id', 'N/A')
                    logger.info(f"Round {i}: Score={round_data.get('score', 'N/A')}, P1={p1_card} (ID: {p1_card_id}), P2={p2_card} (ID: {p2_card_id}), Winner={winner_id_round}")
                
                # Log round winners summary
                if hasattr(match_state, 'round_winners'):
                    p1_wins = sum(1 for w in match_state.round_winners if w == match_state.player1_id)
                    p2_wins = sum(1 for w in match_state.round_winners if w == match_state.player2_id)
                    draws = sum(1 for w in match_state.round_winners if w is None)
                    logger.info(f"Round winners summary: Player 1 wins={p1_wins}, Player 2 wins={p2_wins}, Draws={draws}")
                
                match_record = Match(
                    guild_id=interaction.guild.id,
                    player1_id=match_state.player1_id,
                    player2_id=match_state.player2_id,
                    player1_score=match_state.player1_score,
                    player2_score=match_state.player2_score,
                    winner_id=winner_id,
                    match_details=json.dumps([r for r in match_state.round_history]),
                    completed_at=discord.utils.utcnow()
                )
                session.add(match_record)
                
                # Update user stats
                result = await session.execute(
                    select(User).where(User.id.in_([match_state.player1_id, match_state.player2_id]))
                )
                users = result.scalars().all()
                
                for user in users:
                    user.total_games += 1
                    if winner_id == user.id:
                        user.total_wins += 1
                    elif winner_id is None:
                        user.total_draws += 1
                    else:
                        user.total_losses += 1
                
                # Update leaderboard
                await self._update_leaderboard(
                    session, interaction.guild.id, match_state.player1_id,
                    won=(winner_id == match_state.player1_id),
                    draw=(winner_id is None)
                )
                await self._update_leaderboard(
                    session, interaction.guild.id, match_state.player2_id,
                    won=(winner_id == match_state.player2_id),
                    draw=(winner_id is None)
                )
                
                # Remove active match - handle multiple matches if they exist
                result = await session.execute(
                    select(ActiveMatch).where(ActiveMatch.channel_id == interaction.channel_id)
                )
                active_matches = result.scalars().all()
                for active in active_matches:
                    await session.delete(active)
                
                await session.commit()
                
                # Process any active bets
                await self._process_bets(session, interaction.guild.id, 
                                        match_state.player1_id, match_state.player2_id, winner_id)
            
            # Show match complete embed
            embed = EmbedBuilder.match_complete_embed(match_state, player1.name, player2.name)
            await interaction.channel.send(embed=embed)
            
            # Remove from active matches
            del self.active_matches[interaction.channel_id]
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in _complete_match: {e}", exc_info=True)
            # Try to send error message
            try:
                await interaction.channel.send(
                    "❌ An error occurred while completing the match.",
                )
            except:
                pass
    
    async def _process_bets(self, session: AsyncSession, guild_id: int,
                           player1_id: int, player2_id: int, winner_id: Optional[int]):
        """Process bets for completed match"""
        result = await session.execute(
            select(Bet)
            .where(Bet.guild_id == guild_id)
            .where(Bet.accepted == True)
            .where(Bet.completed == False)
            .where(
                ((Bet.creator_id == player1_id) & (Bet.challenged_id == player2_id)) |
                ((Bet.creator_id == player2_id) & (Bet.challenged_id == player1_id))
            )
        )
        bets = result.scalars().all()
        
        for bet in bets:
            if winner_id is None:
                # Draw - return cards
                bet.completed = True
                continue
            
            # Transfer cards to winner
            # Winner gets the loser's cards
            if winner_id == bet.creator_id:
                # Creator won - they get challenged's cards
                loser_id = bet.challenged_id
                loser_cards = bet.challenged_cards or []
                winner_id_bet = bet.creator_id
            else:
                # Challenged won - they get creator's cards
                loser_id = bet.creator_id
                loser_cards = bet.creator_cards or []
                winner_id_bet = bet.challenged_id
            
            # Remove cards from loser and give to winner
            for card_id in loser_cards:
                # Remove from loser
                result = await session.execute(
                    select(Collection)
                    .where(Collection.user_id == loser_id)
                    .where(Collection.card_id == card_id)
                    .limit(1)
                )
                collection = result.scalar_one_or_none()
                if collection:
                    await session.delete(collection)
                
                # Give to winner
                new_collection = Collection(
                    user_id=winner_id_bet,
                    card_id=card_id
                )
                session.add(new_collection)
            
            bet.completed = True
            bet.winner_id = winner_id
        
        await session.commit()
    
    @app_commands.command(name="bet", description="Bet cards against another user")
    @app_commands.describe(
        opponent="The user you want to bet against",
        card_name="Name of card to bet (use command multiple times for multiple cards)"
    )
    async def create_bet(self, interaction: discord.Interaction, 
                        opponent: discord.Member, card_name: str):
        """Create or add to a bet"""
        # Defer immediately to avoid interaction timeout
        await interaction.response.defer(ephemeral=False)
        
        # Early validation
        if opponent.bot or opponent.id == interaction.user.id:
            await interaction.followup.send(
                "❌ You can't bet against bots or yourself!",
                ephemeral=True
            )
            return
        
        try:
            async with AsyncSessionLocal() as session:
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
                        ephemeral=True
                    )
                    return
                
                card, _ = card_data
                
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
                            "❌ You can only bet up to 3 cards!",
                            ephemeral=True
                        )
                        return
                    
                    existing_bet_as_creator.creator_cards.append(card.id)
                    await session.commit()
                    
                    await interaction.followup.send(
                        f"✅ Added **{card.name}** to your bet against {opponent.mention}!",
                        ephemeral=True
                    )
                elif existing_bet_as_challenged:
                    # User is challenged, accepting the bet by adding their cards
                    if len(existing_bet_as_challenged.challenged_cards) >= 3:
                        await interaction.followup.send(
                            "❌ You can only bet up to 3 cards!",
                            ephemeral=True
                        )
                        return
                    
                    existing_bet_as_challenged.challenged_cards.append(card.id)
                    
                    # Check if both players have matched number of cards
                    if len(existing_bet_as_challenged.challenged_cards) == len(existing_bet_as_challenged.creator_cards):
                        existing_bet_as_challenged.accepted = True
                        await interaction.followup.send(
                            f"✅ Bet accepted! You matched with **{card.name}**.\n"
                            f"🎲 The bet is now active! Winner takes all cards.",
                            ephemeral=False
                        )
                    else:
                        await interaction.followup.send(
                            f"✅ Added **{card.name}** to your bet!\n"
                            f"Match {len(existing_bet_as_challenged.creator_cards)} cards to accept the bet.",
                            ephemeral=False
                        )
                    
                    await session.commit()
                else:
                    # Create new bet
                    new_bet = Bet(
                        guild_id=interaction.guild.id,
                        creator_id=interaction.user.id,
                        challenged_id=opponent.id,
                        creator_cards=[card.id],
                        challenged_cards=[]
                    )
                    session.add(new_bet)
                    await session.commit()
                    
                    embed = discord.Embed(
                        title="🎲 New Bet Created!",
                        description=f"{interaction.user.mention} has challenged {opponent.mention} to a bet!",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="Wagered Card", value=f"**{card.name}**", inline=False)
                    embed.add_field(
                        name="To Accept",
                        value=f"{opponent.mention}, use `/bet {interaction.user.mention} <card_name>` to match the bet!",
                        inline=False
                    )
                    
                    await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in create_bet: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while creating the bet.",
                ephemeral=True
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
                    interaction.guild.name,
                    [(user, lb) for lb, user in entries]
                )
                
                await interaction.followup.send(embed=embed)
        except Exception as e:
            import logging
            logger = logging.getLogger('discord_bot')
            logger.error(f"Error in view_leaderboard: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching the leaderboard.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(MatchCog(bot))

