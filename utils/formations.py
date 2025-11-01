import config
from typing import Dict, Tuple, Optional

class FormationManager:
    """Manages team formations and position validation"""
    
    @staticmethod
    def get_formation(formation_key: str) -> Optional[Dict]:
        """Get formation configuration"""
        return config.FORMATIONS.get(formation_key)
    
    @staticmethod
    def get_all_formations() -> Dict:
        """Get all available formations"""
        return config.FORMATIONS
    
    @staticmethod
    def validate_position_in_formation(position: str, formation_key: str) -> bool:
        """Check if a position exists in a formation"""
        formation = config.FORMATIONS.get(formation_key)
        if not formation:
            return False
        return position in formation['positions']
    
    @staticmethod
    def get_position_bonuses(position: str, formation_key: str) -> Dict[str, int]:
        """Get stat bonuses for a position in a formation"""
        formation = config.FORMATIONS.get(formation_key)
        if not formation:
            return {}
        
        bonuses = formation.get('bonuses', {})
        return bonuses.get(position, {})
    
    @staticmethod
    def calculate_chemistry_links(team_data: Dict) -> int:
        """
        Calculate team chemistry based on player links
        team_data should be: {position: card_object}
        """
        chemistry = 0
        positions = list(team_data.keys())
        
        # Define position adjacencies (which positions are linked)
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
        
        # Check chemistry between adjacent players
        for pos1 in positions:
            card1 = team_data[pos1]
            adjacent_positions = adjacencies.get(pos1, [])
            
            for pos2 in adjacent_positions:
                if pos2 in team_data:
                    card2 = team_data[pos2]
                    
                    # Same club: +2 chemistry
                    if card1.club and card2.club and card1.club == card2.club:
                        chemistry += 2
                    
                    # Same nation: +1 chemistry
                    if card1.nation and card2.nation and card1.nation == card2.nation:
                        chemistry += 1
                    
                    # Same league: +1 chemistry
                    if card1.league and card2.league and card1.league == card2.league:
                        chemistry += 1
        
        return chemistry
    
    @staticmethod
    def apply_formation_bonuses(card, position: str, formation_key: str) -> Tuple[int, int]:
        """
        Apply formation bonuses to card stats
        Returns: (modified_attack, modified_defense)
        """
        bonuses = FormationManager.get_position_bonuses(position, formation_key)
        
        attack = card.attack_stat + bonuses.get('attack', 0)
        defense = card.defense_stat + bonuses.get('defense', 0)
        
        return attack, defense
    
    @staticmethod
    def calculate_team_rating(team_data: Dict, formation_key: str, logo_bonus: int = 0) -> int:
        """Calculate overall team rating with all bonuses"""
        if not team_data:
            return 0
        
        total_rating = 0
        player_count = 0
        
        # Base ratings with formation bonuses
        for position, card in team_data.items():
            attack, defense = FormationManager.apply_formation_bonuses(card, position, formation_key)
            player_rating = (attack + defense) // 2
            total_rating += player_rating
            player_count += 1
        
        if player_count == 0:
            return 0
        
        # Average rating
        avg_rating = total_rating // player_count
        
        # Add chemistry bonus (every 10 chemistry = +1 OVR)
        chemistry = FormationManager.calculate_chemistry_links(team_data)
        chemistry_bonus = chemistry // 10
        
        # Add logo bonus
        final_rating = avg_rating + chemistry_bonus + logo_bonus
        
        return min(99, max(0, final_rating))
    
    @staticmethod
    def get_formation_visual(formation_key: str, team_slots: Dict[str, str]) -> str:
        """
        Generate a visual representation of the formation
        team_slots: {position: player_name}
        """
        formation = config.FORMATIONS.get(formation_key)
        if not formation:
            return "Invalid formation"
        
        # Create a simple text-based formation display
        lines = []
        lines.append(f"**{formation['name']}**\n")
        
        # Group positions by rows
        rows = {}
        for pos, (x, y) in formation['positions'].items():
            if y not in rows:
                rows[y] = []
            rows[y].append((x, pos))
        
        # Sort rows from front to back (smallest y first)
        for y in sorted(rows.keys()):
            row_positions = sorted(rows[y], key=lambda p: p[0])
            row_text = "  ".join([
                f"{pos}({team_slots.get(pos, 'Empty')})" 
                for x, pos in row_positions
            ])
            lines.append(row_text)
        
        return "\n".join(lines)

