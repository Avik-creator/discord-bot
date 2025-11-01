import aiohttp
import config
from typing import Optional, Dict, List
from database.models import Card, CardType
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import random

class APIFootball:
    """Integration with API-Football for player data"""
    
    def __init__(self):
        self.base_url = config.API_FOOTBALL_BASE_URL
        self.api_key = config.API_FOOTBALL_KEY
        self.headers = {
            'x-apisports-key': self.api_key
        }
    
    async def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make an API request"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/{endpoint}",
                    headers=self.headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    return None
        except Exception as e:
            print(f"API Request Error: {e}")
            return None
    
    async def get_players_from_league(self, league_id: int, season: int = 2024) -> List[Dict]:
        """Fetch players from a specific league"""
        endpoint = "players"
        params = {
            'league': league_id,
            'season': season
        }
        response = await self._make_request(endpoint, params)
        if response and 'response' in response:
            return response['response']
        return []
    
    async def get_top_players(self, season: int = 2024) -> List[Dict]:
        """Get top players from major leagues"""
        # Major league IDs: Premier League (39), La Liga (140), Serie A (135), Bundesliga (78), Ligue 1 (61)
        major_leagues = [39, 140, 135, 78, 61]
        all_players = []
        
        for league_id in major_leagues:
            players = await self.get_players_from_league(league_id, season)
            all_players.extend(players[:20])  # Get top 20 from each
        
        return all_players
    
    def _calculate_stats(self, player_stats: Dict) -> tuple:
        """Calculate attack and defense stats from API data"""
        try:
            statistics = player_stats.get('statistics', [{}])[0]
            
            # Get goals, assists, shots for attack
            goals = statistics.get('goals', {}).get('total', 0) or 0
            assists = statistics.get('goals', {}).get('assists', 0) or 0
            shots = statistics.get('shots', {}).get('total', 0) or 0
            
            # Get tackles, interceptions for defense
            tackles = statistics.get('tackles', {}).get('total', 0) or 0
            interceptions = statistics.get('tackles', {}).get('interceptions', 0) or 0
            duels_won = statistics.get('duels', {}).get('won', 0) or 0
            
            # Calculate ratings (scale to 50-99)
            attack_stat = min(99, 50 + (goals * 5) + (assists * 3) + (shots // 10))
            defense_stat = min(99, 50 + (tackles // 2) + (interceptions * 2) + (duels_won // 10))
            
            # Overall is average of both
            overall = (attack_stat + defense_stat) // 2
            
            return overall, attack_stat, defense_stat
        except:
            # Default stats if calculation fails
            return random.randint(65, 85), random.randint(60, 90), random.randint(60, 90)
    
    def _map_position(self, api_position: str) -> str:
        """Map API position to game position"""
        position_map = {
            'Goalkeeper': 'GK',
            'Defender': random.choice(['LB', 'LCB', 'RCB', 'RB']),
            'Midfielder': random.choice(['LCM', 'RCM', 'CDM', 'CAM']),
            'Attacker': random.choice(['LW', 'ST', 'RW'])
        }
        return position_map.get(api_position, random.choice(config.VALID_POSITIONS))
    
    async def cache_player_to_db(self, session: AsyncSession, player_data: Dict, card_type: CardType = CardType.BASE) -> Optional[Card]:
        """Cache a player from API to database"""
        try:
            player = player_data.get('player', {})
            statistics = player_data.get('statistics', [{}])[0]
            
            # Check if player already exists
            result = await session.execute(
                select(Card).where(Card.api_player_id == player['id'])
            )
            existing_card = result.scalar_one_or_none()
            
            if existing_card:
                return existing_card
            
            # Calculate stats
            overall, attack, defense = self._calculate_stats(player_data)
            
            # Get position
            position = self._map_position(statistics.get('games', {}).get('position', 'Midfielder'))
            
            # Get team and league info
            team = statistics.get('team', {})
            league = statistics.get('league', {})
            
            # Create new card
            new_card = Card(
                api_player_id=player['id'],
                name=player['name'],
                position=position,
                overall_rating=overall,
                attack_stat=attack,
                defense_stat=defense,
                club=team.get('name'),
                nation=player.get('nationality'),
                league=league.get('name'),
                card_type=card_type,
                photo_url=player.get('photo')
            )
            
            session.add(new_card)
            await session.commit()
            await session.refresh(new_card)
            
            return new_card
        except Exception as e:
            print(f"Error caching player: {e}")
            await session.rollback()
            return None
    
    async def populate_database(self, session: AsyncSession, count: int = 100):
        """Populate database with players from API"""
        players = await self.get_top_players()
        cached_count = 0
        
        for player_data in players[:count]:
            card = await self.cache_player_to_db(session, player_data)
            if card:
                cached_count += 1
        
        return cached_count
    
    async def get_random_card_from_db(self, session: AsyncSession, card_type: CardType = None) -> Optional[Card]:
        """Get a random card from database"""
        try:
            query = select(Card)
            if card_type:
                query = query.where(Card.card_type == card_type)
            
            result = await session.execute(query)
            cards = result.scalars().all()
            
            if cards:
                return random.choice(cards)
            return None
        except Exception as e:
            print(f"Error getting random card: {e}")
            return None

