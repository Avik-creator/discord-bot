# Advanced Configuration Guide

This guide covers advanced configuration options for customizing your Football Card Discord Bot.

## Environment Variables

### Required Settings

```env
# Discord Bot Token (required)
DISCORD_BOT_TOKEN=your_token_here

# PostgreSQL Database (required)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=discord_bot
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password

# API-Football (required for real player data)
API_FOOTBALL_KEY=your_api_key_here
```

### Optional Settings

```env
# Patreon store link
PATREON_STORE_LINK=https://patreon.com/yourstore

# Card spawning configuration
SPAWN_MESSAGE_MIN=20          # Minimum messages before spawn
SPAWN_MESSAGE_MAX=50          # Maximum messages before spawn
CATCH_TIMEOUT_SECONDS=180     # Time to catch spawned card
```

## Formations Configuration

Edit `config.py` to customize formations:

### Adding a New Formation

```python
FORMATIONS = {
    'your_formation_key': {
        'name': 'Display Name',
        'positions': {
            'GK': (5, 10),    # (x, y) coordinates
            'LB': (2, 8),
            # ... add all 11 positions
        },
        'bonuses': {
            'ST': {'attack': 3},     # +3 attack for strikers
            'CDM': {'defense': 2},   # +2 defense for CDM
            # ... position-specific bonuses
        }
    }
}
```

### Formation Bonus System

Each formation can apply bonuses to specific positions:

- `attack`: Increases attack stat
- `defense`: Increases defense stat
- Can be positive or negative (e.g., -1 defense for attacking formations)

Example:
```python
'bonuses': {
    'ST': {'attack': 3},          # Striker gets +3 attack
    'LW': {'attack': 2},          # Left wing gets +2 attack
    'CDM': {'defense': 2},        # CDM gets +2 defense
    'CAM': {'attack': 1, 'defense': -1}  # CAM: +1 attack, -1 defense
}
```

## Chemistry System Configuration

Edit `utils/formations.py` to customize chemistry calculations:

### Chemistry Link Values

Current values (in `FormationManager.calculate_chemistry_links`):
```python
# Same club: +2 chemistry per link
if card1.club == card2.club:
    chemistry += 2

# Same nation: +1 chemistry per link
if card1.nation == card2.nation:
    chemistry += 1

# Same league: +1 chemistry per link
if card1.league == card2.league:
    chemistry += 1
```

### Position Adjacencies

Define which positions are linked:
```python
adjacencies = {
    'GK': ['LCB', 'RCB'],
    'LCB': ['GK', 'LB', 'RCB', 'CDM'],
    # ... customize links between positions
}
```

## Match Engine Configuration

### Attack vs Defense Variance

In `utils/match_engine.py`, adjust randomness:

```python
# Add variance (±5 points by default)
attack_roll = attack_stat + random.randint(-5, 5)
defense_roll = defense_stat + random.randint(-5, 5)
```

Increase for more randomness:
```python
attack_roll = attack_stat + random.randint(-10, 10)  # More variance
```

### Chemistry Bonus per Player

In `MatchEngine.calculate_player_effective_stat`:
```python
chemistry_bonus = MatchEngine._calculate_player_chemistry(position, card, team_data)
stat += chemistry_bonus  # 1:1 ratio

# Or scale it:
stat += chemistry_bonus * 0.5  # Half the chemistry bonus
```

## Card Stats Configuration

### API-Football Stat Calculation

In `utils/api_football.py`, customize how stats are calculated:

```python
def _calculate_stats(self, player_stats: Dict) -> tuple:
    # Customize these formulas
    attack_stat = min(99, 50 + (goals * 5) + (assists * 3) + (shots // 10))
    defense_stat = min(99, 50 + (tackles // 2) + (interceptions * 2) + (duels_won // 10))
    overall = (attack_stat + defense_stat) // 2
    
    return overall, attack_stat, defense_stat
```

### Position Mapping

Customize how API positions map to game positions:

```python
def _map_position(self, api_position: str) -> str:
    position_map = {
        'Goalkeeper': 'GK',
        'Defender': random.choice(['LB', 'LCB', 'RCB', 'RB']),
        'Midfielder': random.choice(['LCM', 'RCM', 'CDM', 'CAM']),
        'Attacker': random.choice(['LW', 'ST', 'RW'])
    }
    return position_map.get(api_position, 'ST')
```

## Cooldown Configuration

Edit `config.py` to customize cooldowns (in seconds):

```python
COOLDOWNS = {
    'daily_pack': 86400,      # 24 hours
    'weekly_pack': 604800,    # 7 days
    'event_pack': 604800,     # 7 days
    'premium_pack': 172800,   # 2 days
    'booster_pack': 172800,   # 2 days
    'vote': 86400             # 24 hours
}
```

## Logo Rarity Configuration

Edit `config.py` for logo bonuses:

```python
LOGO_RARITIES = {
    'common': 1,      # +1 OVR
    'rare': 2,        # +2 OVR
    'legendary': 3    # +3 OVR
}
```

## Card Types and Events

### Adding New Event Types

In `config.py`:

```python
EVENT_TYPES = [
    'TOTW',           # Team of the Week
    'TOTS',           # Team of the Season
    'TOTY',           # Team of the Year
    'UCL',            # UEFA Champions League
    'UEL',            # UEFA Europa League
    'International',  # International cards
    'Special',        # Special events
    'YOUR_EVENT'      # Add custom events here
]
```

## Database Configuration

### Connection Pool Settings

In `database/database.py`:

```python
engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,              # Set True for SQL query logging
    poolclass=NullPool,      # Use different pool if needed
    pool_pre_ping=True,      # Keep connections alive
    pool_size=10,            # Max connections (add if using pool)
    max_overflow=20          # Extra connections (add if using pool)
)
```

### Query Optimization

For large databases, add indexes to `database/models.py`:

```python
from sqlalchemy import Index

class Card(Base):
    __tablename__ = 'cards'
    # ... existing fields ...
    
    # Add indexes
    __table_args__ = (
        Index('idx_card_name', 'name'),
        Index('idx_card_club', 'club'),
        Index('idx_card_ovr', 'overall_rating'),
    )
```

## Bot Behavior Configuration

### Presence/Status

In `bot.py`, customize bot status:

```python
await self.change_presence(
    activity=discord.Game(name="⚽ /help | Football Cards"),
    status=discord.Status.online  # online, idle, dnd, invisible
)
```

Rotating status:
```python
activities = [
    discord.Game(name="⚽ Football Cards"),
    discord.Activity(type=discord.ActivityType.watching, name="matches"),
    discord.Activity(type=discord.ActivityType.competing, name="tournaments")
]
```

### Logging Configuration

In `bot.py`:

```python
logging.basicConfig(
    level=logging.INFO,      # DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),  # Log to file
        logging.StreamHandler()          # Log to console
    ]
)
```

## Performance Tuning

### Card Spawning Rate

Adjust message threshold based on server activity:

```python
# For high-activity servers
SPAWN_MESSAGE_MIN=50
SPAWN_MESSAGE_MAX=100

# For low-activity servers
SPAWN_MESSAGE_MIN=10
SPAWN_MESSAGE_MAX=20
```

### Database Query Optimization

Add pagination limits in cogs:

```python
# In collection.py
cards_per_page = 10  # Increase to 20 or 25 for faster browsing
```

### Caching

Implement caching for frequently accessed data:

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_formation(formation_key: str):
    return config.FORMATIONS.get(formation_key)
```

## Security Considerations

### Admin Command Restrictions

Additional permission checks can be added:

```python
@app_commands.checks.has_permissions(administrator=True)
@app_commands.checks.has_role("Bot Admin")  # Require specific role
async def admin_command(self, interaction):
    # ... command logic
```

### Rate Limiting

Implement command cooldowns:

```python
from discord.ext import commands

@commands.cooldown(1, 60, commands.BucketType.user)  # 1 use per 60s per user
async def expensive_command(self, interaction):
    # ... command logic
```

## Customization Ideas

### Custom Card Designs
- Add image generation with Pillow
- Create custom card templates
- Add club badges and flags

### Additional Features
- Tournament system
- Trading system between users
- Card upgrade system
- Daily quests/challenges
- Seasonal events

### Gamification
- Achievement system
- Level/XP system
- Card fusion/evolution
- Pack opening animations

## Monitoring and Maintenance

### Health Checks

Add a health check endpoint or command:

```python
@app_commands.command(name="status")
async def bot_status(self, interaction):
    # Report bot health, database status, etc.
    pass
```

### Backup Strategy

Regular database backups:
```bash
# Automated backup script
pg_dump discord_bot > backup_$(date +%Y%m%d).sql
```

### Log Rotation

Use logrotate or similar tool to manage log files.

---

For more information, see:
- [README.md](README.md) - General documentation
- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
- [TESTING.md](TESTING.md) - Testing checklist

