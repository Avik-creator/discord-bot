import random
from typing import Dict, Tuple, Optional
from database.models import Card
from utils.formations import FormationManager

class MatchEngine:
    """Handles match simulation with chemistry and formations"""
    
    @staticmethod
    def calculate_player_effective_stat(card: Card, position: str, formation: str, 
                                       team_data: Dict, is_attacking: bool) -> int:
        """
        Calculate effective stat for a player considering all bonuses
        """
        # Base stat
        if is_attacking:
            base_stat = card.attack_stat
        else:
            base_stat = card.defense_stat
        
        # Apply formation bonuses
        attack_bonus, defense_bonus = FormationManager.apply_formation_bonuses(card, position, formation)
        if is_attacking:
            stat = attack_bonus
        else:
            stat = defense_bonus
        
        # Add chemistry bonus (calculate chemistry for just this player's links)
        chemistry_bonus = MatchEngine._calculate_player_chemistry(position, card, team_data)
        stat += chemistry_bonus
        
        return min(99, max(0, stat))
    
    @staticmethod
    def _calculate_player_chemistry(position: str, card: Card, team_data: Dict) -> int:
        """Calculate chemistry bonus for individual player"""
        chemistry = 0
        
        # Define position adjacencies
        adjacencies = {
            'GK': ['LCB', 'RCB'],
            'LB': ['LCB', 'LCM'],
            'LCB': ['GK', 'LB', 'RCB', 'CDM'],
            'RCB': ['GK', 'RB', 'LCB', 'CDM'],
            'RB': ['RCB', 'RCM'],
            'CDM': ['LCB', 'RCB', 'LCM', 'RCM', 'CAM'],
            'LCM': ['LB', 'CDM', 'LW', 'CAM'],
            'RCM': ['RB', 'CDM', 'RW', 'CAM'],
            'CAM': ['CDM', 'LCM', 'RCM', 'ST', 'LW', 'RW'],
            'LW': ['LCM', 'CAM', 'ST'],
            'ST': ['CAM', 'LW', 'RW'],
            'RW': ['RCM', 'CAM', 'ST']
        }
        
        adjacent_positions = adjacencies.get(position, [])
        
        for adj_pos in adjacent_positions:
            if adj_pos in team_data:
                adj_card = team_data[adj_pos]
                
                # Same club: +1 per link
                if card.club and adj_card.club and card.club == adj_card.club:
                    chemistry += 1
                
                # Same nation: +0.5 per link
                if card.nation and adj_card.nation and card.nation == adj_card.nation:
                    chemistry += 0.5
                
                # Same league: +0.5 per link
                if card.league and adj_card.league and card.league == adj_card.league:
                    chemistry += 0.5
        
        return int(chemistry)
    
    @staticmethod
    def simulate_round(attacker_card: Card, attacker_position: str, attacker_formation: str, attacker_team: Dict,
                      defender_card: Card, defender_position: str, defender_formation: str, defender_team: Dict) -> Tuple[str, Dict]:
        """
        Simulate a single round: attack vs defense
        Returns: (result, details)
        result can be: 'attacker_wins', 'defender_wins', 'draw'
        """
        # Calculate effective stats
        attack_stat = MatchEngine.calculate_player_effective_stat(
            attacker_card, attacker_position, attacker_formation, attacker_team, is_attacking=True
        )
        
        defense_stat = MatchEngine.calculate_player_effective_stat(
            defender_card, defender_position, defender_formation, defender_team, is_attacking=False
        )
        
        # Add some variance (±5 points)
        attack_roll = attack_stat + random.randint(-5, 5)
        defense_roll = defense_stat + random.randint(-5, 5)
        
        # Determine winner
        if attack_roll > defense_roll:
            result = 'attacker_wins'
        elif defense_roll > attack_roll:
            result = 'defender_wins'
        else:
            result = 'draw'
        
        details = {
            'attacker': {
                'card': attacker_card.name,
                'position': attacker_position,
                'base_attack': attacker_card.attack_stat,
                'effective_attack': attack_stat,
                'roll': attack_roll
            },
            'defender': {
                'card': defender_card.name,
                'position': defender_position,
                'base_defense': defender_card.defense_stat,
                'effective_defense': defense_stat,
                'roll': defense_roll
            },
            'result': result
        }
        
        return result, details
    
    @staticmethod
    def calculate_match_result(player1_score: int, player2_score: int) -> Tuple[Optional[int], str]:
        """
        Calculate match result
        Returns: (winner_id or None for draw, result_text)
        """
        if player1_score > player2_score:
            return 1, "Player 1 Wins!"
        elif player2_score > player1_score:
            return 2, "Player 2 Wins!"
        else:
            return None, "Draw!"
    
    @staticmethod
    def calculate_points(won: bool, draw: bool) -> int:
        """Calculate leaderboard points"""
        if won:
            return 3
        elif draw:
            return 1
        else:
            return 0

class MatchState:
    """Tracks state of an ongoing match"""
    
    def __init__(self, player1_id: int, player2_id: int, 
                 player1_team: Dict, player2_team: Dict,
                 player1_formation: str, player2_formation: str):
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.player1_team = player1_team  # {position: card}
        self.player2_team = player2_team
        self.player1_formation = player1_formation
        self.player2_formation = player2_formation
        
        self.current_round = 1
        self.max_rounds = 11
        
        self.player1_score = 0
        self.player2_score = 0
        
        self.player1_used_cards = set()
        self.player2_used_cards = set()
        
        self.round_history = []
        
        self.current_turn = player1_id  # Who selects next
    
    def get_available_cards(self, player_id: int) -> Dict:
        """Get cards that haven't been used yet"""
        if player_id == self.player1_id:
            used = self.player1_used_cards
            team = self.player1_team
        else:
            used = self.player2_used_cards
            team = self.player2_team
        
        return {pos: card for pos, card in team.items() if pos not in used}
    
    def select_card(self, player_id: int, position: str) -> bool:
        """Mark a card as selected for this round"""
        available = self.get_available_cards(player_id)
        
        if position not in available:
            return False
        
        if player_id == self.player1_id:
            self.player1_used_cards.add(position)
        else:
            self.player2_used_cards.add(position)
        
        return True
    
    def play_round(self, player1_position: str, player2_position: str) -> Dict:
        """Play a round and update scores"""
        # Get cards
        player1_card = self.player1_team[player1_position]
        player2_card = self.player2_team[player2_position]
        
        # Alternate who attacks (odd rounds: player1 attacks, even rounds: player2 attacks)
        if self.current_round % 2 == 1:
            result, details = MatchEngine.simulate_round(
                player1_card, player1_position, self.player1_formation, self.player1_team,
                player2_card, player2_position, self.player2_formation, self.player2_team
            )
            
            if result == 'attacker_wins':
                self.player1_score += 1
            elif result == 'defender_wins':
                self.player2_score += 1
        else:
            result, details = MatchEngine.simulate_round(
                player2_card, player2_position, self.player2_formation, self.player2_team,
                player1_card, player1_position, self.player1_formation, self.player1_team
            )
            
            if result == 'attacker_wins':
                self.player2_score += 1
            elif result == 'defender_wins':
                self.player1_score += 1
        
        # Store round result
        round_data = {
            'round': self.current_round,
            'player1_card': player1_card.name,
            'player1_position': player1_position,
            'player2_card': player2_card.name,
            'player2_position': player2_position,
            'details': details,
            'score': f"{self.player1_score} - {self.player2_score}"
        }
        
        self.round_history.append(round_data)
        
        # Switch turn
        self.current_turn = self.player2_id if self.current_turn == self.player1_id else self.player1_id
        self.current_round += 1
        
        return round_data
    
    def is_complete(self) -> bool:
        """Check if match is complete"""
        return self.current_round > self.max_rounds
    
    def get_winner(self) -> Optional[int]:
        """Get winner ID or None for draw"""
        if self.player1_score > self.player2_score:
            return self.player1_id
        elif self.player2_score > self.player1_score:
            return self.player2_id
        return None

