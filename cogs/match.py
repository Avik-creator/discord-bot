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

class MatchCog(commands.Cog):
    """Match and betting commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_matches = {}  # {channel_id: MatchState}
    
    async def _get_team_data(self, session: AsyncSession, user_id: int) -> tuple[Optional[Team], Dict]:
        """Get team and slots for a user"""
        result = await session.execute(
            select(Team).where(Team.user_id == user_id)
        )
        team = result.scalar_one_or_none()
        
        if not team or not team.formation:
            return None, {}
        
        # Get team slots
        result = await session.execute(
            select(TeamSlot, Card)
            .join(Card, TeamSlot.card_id == Card.id)
            .where(TeamSlot.team_id == team.id)
        )
        slots = result.all()
        
        team_slots = {slot.position: card for slot, card in slots}
        
        # Ensure we have 11 players
        if len(team_slots) < 11:
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
        if opponent.bot or opponent.id == interaction.user.id:
            await interaction.response.send_message(
                "❌ You can't challenge bots or yourself!",
                ephemeral=True
            )
            return
        
        # Check if there's already an active match in this channel
        if interaction.channel_id in self.active_matches:
            await interaction.response.send_message(
                "❌ There's already an active match in this channel!",
                ephemeral=True
            )
            return
        
        async with AsyncSessionLocal() as session:
            # Get both teams
            player1_team, player1_slots = await self._get_team_data(session, interaction.user.id)
            player2_team, player2_slots = await self._get_team_data(session, opponent.id)
            
            if not player1_team or not player1_slots:
                await interaction.response.send_message(
                    "❌ You need a complete team with 11 players to play!",
                    ephemeral=True
                )
                return
            
            if not player2_team or not player2_slots:
                await interaction.response.send_message(
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
            embed.add_field(
                name="Current Turn",
                value=f"{interaction.user.mention} - use `/select <player_name>` to choose!",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="select", description="Select a player for the current round")
    @app_commands.describe(player_name="Name of the player to use this round")
    async def select_player(self, interaction: discord.Interaction, player_name: str):
        """Select a player for the current match round"""
        # Check if there's an active match
        if interaction.channel_id not in self.active_matches:
            await interaction.response.send_message(
                "❌ No active match in this channel!",
                ephemeral=True
            )
            return
        
        match_state = self.active_matches[interaction.channel_id]
        
        # Check if it's this user's turn
        if match_state.current_turn != interaction.user.id:
            await interaction.response.send_message(
                "❌ It's not your turn!",
                ephemeral=True
            )
            return
        
        # Get available cards
        available_cards = match_state.get_available_cards(interaction.user.id)
        
        # Find matching card
        selected_position = None
        for position, card in available_cards.items():
            if card.name.lower() == player_name.lower() or player_name.lower() in card.name.lower():
                selected_position = position
                break
        
        if not selected_position:
            await interaction.response.send_message(
                f"❌ You don't have an available player matching '{player_name}'!",
                ephemeral=True
            )
            return
        
        # Mark card as selected
        match_state.select_card(interaction.user.id, selected_position)
        
        # Check if both players have selected
        if match_state.current_turn == match_state.player1_id:
            # Player 1 selected, now wait for player 2
            await interaction.response.send_message(
                f"✅ You selected **{available_cards[selected_position].name}**!\n"
                f"Waiting for <@{match_state.player2_id}>...",
                ephemeral=True
            )
            
            # Notify player 2
            player2 = await self.bot.fetch_user(match_state.player2_id)
            embed = discord.Embed(
                title="⚽ Your Turn!",
                description=f"Use `/select <player_name>` to choose your player for Round {match_state.current_round}",
                color=discord.Color.blue()
            )
            available_p2 = match_state.get_available_cards(match_state.player2_id)
            available_names = [card.name for card in available_p2.values()]
            embed.add_field(
                name="Available Players",
                value=", ".join(available_names[:10]) + ("..." if len(available_names) > 10 else ""),
                inline=False
            )
            
            try:
                await interaction.channel.send(f"<@{match_state.player2_id}>", embed=embed)
            except:
                pass
        else:
            # Player 2 selected, now play the round
            await interaction.response.defer()
            
            # Get both selected positions
            player1_used = list(match_state.player1_used_cards)
            player2_used = list(match_state.player2_used_cards)
            
            player1_position = player1_used[-1]
            player2_position = selected_position
            
            # Play round
            round_data = match_state.play_round(player1_position, player2_position)
            
            # Show round result
            player1 = await self.bot.fetch_user(match_state.player1_id)
            player2 = await self.bot.fetch_user(match_state.player2_id)
            
            embed = EmbedBuilder.match_round_embed(
                round_data,
                player1.name,
                player2.name
            )
            
            await interaction.followup.send(embed=embed)
            
            # Check if match is complete
            if match_state.is_complete():
                await self._complete_match(interaction, match_state)
            else:
                # Next round
                next_player = await self.bot.fetch_user(match_state.current_turn)
                embed = discord.Embed(
                    title=f"⚽ Round {match_state.current_round}",
                    description=f"{next_player.mention}, use `/select <player_name>` to choose!",
                    color=discord.Color.blue()
                )
                await interaction.channel.send(embed=embed)
    
    async def _complete_match(self, interaction: discord.Interaction, match_state: MatchState):
        """Complete a match and update records"""
        async with AsyncSessionLocal() as session:
            # Get users
            player1 = await self.bot.fetch_user(match_state.player1_id)
            player2 = await self.bot.fetch_user(match_state.player2_id)
            
            # Create match record
            winner_id = match_state.get_winner()
            
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
            
            # Remove active match
            await session.execute(
                select(ActiveMatch)
                .where(ActiveMatch.channel_id == interaction.channel_id)
            )
            result = await session.execute(
                select(ActiveMatch).where(ActiveMatch.channel_id == interaction.channel_id)
            )
            active = result.scalar_one_or_none()
            if active:
                await session.delete(active)
            
            await session.commit()
            
            # Show match complete embed
            embed = EmbedBuilder.match_complete_embed(match_state, player1.name, player2.name)
            await interaction.channel.send(embed=embed)
            
            # Process any active bets
            await self._process_bets(session, interaction.guild.id, 
                                    match_state.player1_id, match_state.player2_id, winner_id)
            
            # Remove from active matches
            del self.active_matches[interaction.channel_id]
    
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
            if winner_id == bet.creator_id:
                loser_id = bet.challenged_id
                loser_cards = bet.challenged_cards
                winner_id_bet = bet.creator_id
            else:
                loser_id = bet.creator_id
                loser_cards = bet.creator_cards
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
        if opponent.bot or opponent.id == interaction.user.id:
            await interaction.response.send_message(
                "❌ You can't bet against bots or yourself!",
                ephemeral=True
            )
            return
        
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
                await interaction.response.send_message(
                    f"❌ You don't have a card matching '{card_name}'!",
                    ephemeral=True
                )
                return
            
            card, _ = card_data
            
            # Check for existing bet
            result = await session.execute(
                select(Bet)
                .where(Bet.guild_id == interaction.guild.id)
                .where(Bet.creator_id == interaction.user.id)
                .where(Bet.challenged_id == opponent.id)
                .where(Bet.accepted == False)
            )
            existing_bet = result.scalar_one_or_none()
            
            if existing_bet:
                # Add to existing bet
                if len(existing_bet.creator_cards) >= 3:
                    await interaction.response.send_message(
                        "❌ You can only bet up to 3 cards!",
                        ephemeral=True
                    )
                    return
                
                existing_bet.creator_cards.append(card.id)
                await session.commit()
                
                await interaction.response.send_message(
                    f"✅ Added **{card.name}** to your bet against {opponent.mention}!",
                    ephemeral=True
                )
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
                
                await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="leaderboard", description="View the server leaderboard")
    async def view_leaderboard(self, interaction: discord.Interaction):
        """Show server leaderboard"""
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
            
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(MatchCog(bot))

