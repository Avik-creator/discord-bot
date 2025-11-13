import discord
from typing import List, Dict, Optional
from database.models import Card, User, Team, Match
from datetime import datetime

class EmbedBuilder:
    """Creates formatted Discord embeds for the bot"""
    
    @staticmethod
    def card_embed(card: Card, show_full: bool = False) -> discord.Embed:
        """Create an embed for displaying a card"""
        # Color based on overall rating
        if card.overall_rating >= 90:
            color = discord.Color.gold()
        elif card.overall_rating >= 85:
            color = discord.Color.purple()
        elif card.overall_rating >= 80:
            color = discord.Color.blue()
        else:
            color = discord.Color.green()
        
        embed = discord.Embed(
            title=f"{card.name}",
            color=color
        )
        
        embed.add_field(name="Position", value=card.position, inline=True)
        embed.add_field(name="Overall", value=f"{card.overall_rating} OVR", inline=True)
        embed.add_field(name="Type", value=card.card_type.value.upper(), inline=True)
        
        if show_full:
            embed.add_field(name="Attack", value=str(card.attack_stat), inline=True)
            embed.add_field(name="Defense", value=str(card.defense_stat), inline=True)
            embed.add_field(name="━━━━━━━━━━", value="", inline=False)
            
            if card.club:
                embed.add_field(name="Club", value=card.club, inline=True)
            if card.nation:
                embed.add_field(name="Nation", value=card.nation, inline=True)
            if card.league:
                embed.add_field(name="League", value=card.league, inline=True)
            
            if card.event_type:
                embed.add_field(name="Event", value=card.event_type, inline=True)
        
        if card.photo_url:
            embed.set_thumbnail(url=card.photo_url)
        
        return embed
    
    @staticmethod
    def collection_embed(user: User, cards: List[Card], page: int, total_pages: int, 
                        sort_by: str = "ovr") -> discord.Embed:
        """Create an embed for displaying user's collection"""
        embed = discord.Embed(
            title=f"{user.username}'s Collection",
            description=f"Total Cards: {len(cards)} | Page {page}/{total_pages}",
            color=discord.Color.blue()
        )
        
        # Group cards by position or show list
        cards_text = []
        for i, card in enumerate(cards[:10], 1):  # Show 10 per page
            cards_text.append(
                f"{i}. **{card.name}** - {card.position} ({card.overall_rating} OVR) - {card.card_type.value}"
            )
        
        embed.add_field(
            name=f"Sorted by: {sort_by}",
            value="\n".join(cards_text) if cards_text else "No cards found",
            inline=False
        )
        
        embed.set_footer(text=f"Use /show <player_name> to see card details")
        
        return embed
    
    @staticmethod
    def team_embed(user: User, team: Team, team_slots: Dict, logo_bonus: int = 0) -> discord.Embed:
        """Create an embed for displaying user's team"""
        from utils.formations import FormationManager
        
        embed = discord.Embed(
            title=f"{user.username}'s Team",
            color=discord.Color.green()
        )
        
        if not team.formation:
            embed.description = "No formation selected. Use `/select lineup` to choose one."
            return embed
        
        formation = FormationManager.get_formation(team.formation)
        if formation:
            embed.add_field(name="Formation", value=formation['name'], inline=True)
        
        if team.logo:
            embed.add_field(name="Logo", value=f"{team.logo.name} (+{logo_bonus} OVR)", inline=True)
        
        # Calculate team rating
        team_data = {pos: card for pos, card in team_slots.items() if card}
        if team_data:
            rating = FormationManager.calculate_team_rating(team_data, team.formation, logo_bonus)
            embed.add_field(name="Team Rating", value=f"{rating} OVR", inline=True)
        
        # Show positions
        positions_text = []
        ordered_positions = []
        if formation:
            ordered_positions = sorted(
                formation['positions'].items(),
                key=lambda item: (item[1][1], item[1][0])
            )
        else:
            ordered_positions = [(pos, None) for pos in sorted(team_slots.keys())]
        
        seen_positions = set()
        for position, _ in ordered_positions:
            seen_positions.add(position)
            card = team_slots.get(position)
            if card:
                positions_text.append(f"**{position}**: {card.name} ({card.overall_rating} OVR)")
            else:
                positions_text.append(f"**{position}**: Empty")
        
        # Include any extra positions not defined in the formation (fallback)
        extra_positions = [pos for pos in sorted(team_slots.keys()) if pos not in seen_positions]
        for position in extra_positions:
            card = team_slots[position]
            positions_text.append(f"**{position}**: {card.name} ({card.overall_rating} OVR)")
        
        embed.add_field(name="Players", value="\n".join(positions_text), inline=False)
        
        return embed
    
    @staticmethod
    def match_round_embed(round_data: Dict, player1_name: str, player2_name: str) -> discord.Embed:
        """Create an embed for a match round result"""
        embed = discord.Embed(
            title=f"⚽ Round {round_data['round']} Result",
            color=discord.Color.blue()
        )
        
        details = round_data['details']
        
        # Player 1 info
        p1_text = (
            f"**{round_data['player1_card']}** ({round_data['player1_position']})\n"
            f"Attack: {details['attacker']['effective_attack']} (Roll: {details['attacker']['roll']})"
        )
        embed.add_field(name=f"🔵 {player1_name}", value=p1_text, inline=True)
        
        # VS
        embed.add_field(name="⚔️", value="VS", inline=True)
        
        # Player 2 info
        p2_text = (
            f"**{round_data['player2_card']}** ({round_data['player2_position']})\n"
            f"Defense: {details['defender']['effective_defense']} (Roll: {details['defender']['roll']})"
        )
        embed.add_field(name=f"🔴 {player2_name}", value=p2_text, inline=True)
        
        # Result
        result = details['result']
        if result == 'attacker_wins':
            winner = player1_name
        elif result == 'defender_wins':
            winner = player2_name
        else:
            winner = "Draw"
        
        embed.add_field(name="Winner", value=f"🏆 {winner}", inline=False)
        embed.add_field(name="Current Score", value=round_data['score'], inline=False)
        
        return embed
    
    @staticmethod
    def match_complete_embed(match_state, player1_name: str, player2_name: str) -> discord.Embed:
        """Create an embed for match completion"""
        winner_id = match_state.get_winner()
        
        if winner_id == match_state.player1_id:
            color = discord.Color.green()
            winner_name = player1_name
        elif winner_id == match_state.player2_id:
            color = discord.Color.red()
            winner_name = player2_name
        else:
            color = discord.Color.grey()
            winner_name = "Draw"
        
        embed = discord.Embed(
            title="🏆 Match Complete!",
            description=f"**{winner_name}** wins!" if winner_id else "It's a draw!",
            color=color
        )
        
        embed.add_field(
            name="Final Score",
            value=f"{player1_name}: {match_state.player1_score}\n{player2_name}: {match_state.player2_score}",
            inline=False
        )
        
        # Show round summary
        rounds_summary = []
        for round_data in match_state.round_history[-5:]:  # Last 5 rounds
            rounds_summary.append(f"Round {round_data['round']}: {round_data['score']}")
        
        if rounds_summary:
            embed.add_field(
                name="Recent Rounds",
                value="\n".join(rounds_summary),
                inline=False
            )
        
        return embed
    
    @staticmethod
    def leaderboard_embed(guild_name: str, entries: List[tuple], page: int = 1) -> discord.Embed:
        """Create an embed for the leaderboard"""
        embed = discord.Embed(
            title=f"🏆 {guild_name} Leaderboard",
            description=f"Win = 3 pts | Draw = 1 pt | Loss = 0 pts",
            color=discord.Color.gold()
        )
        
        if not entries:
            embed.add_field(name="No Data", value="No matches played yet!", inline=False)
            return embed
        
        # Show top 10
        leaderboard_text = []
        for i, (user, lb_entry) in enumerate(entries[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            leaderboard_text.append(
                f"{medal} **{user.username}** - {lb_entry.points} pts "
                f"({lb_entry.wins}W-{lb_entry.draws}D-{lb_entry.losses}L)"
            )
        
        embed.add_field(
            name="Rankings",
            value="\n".join(leaderboard_text),
            inline=False
        )
        
        return embed
    
    @staticmethod
    def stats_embed(user: User) -> discord.Embed:
        """Create an embed for user statistics"""
        embed = discord.Embed(
            title=f"📊 {user.username}'s Statistics",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Total Games", value=str(user.total_games), inline=True)
        embed.add_field(name="Wins", value=str(user.total_wins), inline=True)
        embed.add_field(name="Draws", value=str(user.total_draws), inline=True)
        embed.add_field(name="Losses", value=str(user.total_losses), inline=True)
        embed.add_field(name="Cards Collected", value=str(user.cards_collected), inline=True)
        
        # Win rate
        if user.total_games > 0:
            win_rate = (user.total_wins / user.total_games) * 100
            embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)
        
        return embed
    
    @staticmethod
    def help_embed(category: str = "main") -> discord.Embed:
        """Create help embed for different categories"""
        embed = discord.Embed(
            title="⚽ Football Card Bot - Help",
            color=discord.Color.blue()
        )
        
        if category == "main":
            embed.description = "Welcome to the Football Card Collection Bot! Choose a category:"
            embed.add_field(
                name="📦 Collection Commands",
                value="`/help collection` - View collection & pack commands",
                inline=False
            )
            embed.add_field(
                name="⚽ Team Commands",
                value="`/help team` - View team management commands",
                inline=False
            )
            embed.add_field(
                name="🎮 Match Commands",
                value="`/help match` - View match & betting commands",
                inline=False
            )
            embed.add_field(
                name="👑 Admin Commands",
                value="`/help admin` - View admin-only commands",
                inline=False
            )
        
        return embed

