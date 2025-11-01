# ⚽ Football Card Discord Bot

A comprehensive Discord bot for collecting, trading, and battling with football player cards. Features include card spawning, team management, turn-based matches with chemistry systems, and competitive leaderboards.

## Features

### 🎴 Card Collection System
- **Dynamic Card Spawning**: Cards spawn automatically based on chat activity
- **Multiple Pack Types**: Daily, weekly, event, premium, and booster packs
- **Card Rarity System**: Base cards, Icon cards, and Event cards (TOTW, TOTS, TOTY, etc.)
- **Real Player Data**: Integration with API-Football for authentic player statistics

### ⚽ Team Management
- **Multiple Formations**: 
  - 4-3-3 Attack
  - 4-3-3 Defense
  - 4-4-2 Diamond
  - 4-2-4
  - 3-4-3 Diamond
- **Position System**: 12 positions (LW, ST, RW, CAM, LCM, RCM, CDM, LB, LCB, RCB, RB, GK)
- **Team Logos**: Add logos for +1/+2/+3 OVR bonuses based on rarity

### 🎮 Match System
- **Turn-Based Battles**: 11-round matches with strategic card selection
- **Chemistry System**: Players gain bonuses based on:
  - Same club (+2 chemistry per link)
  - Same nation (+1 chemistry per link)
  - Same league (+1 chemistry per link)
- **Formation Bonuses**: Each formation provides unique stat bonuses to specific positions
- **Betting System**: Wager up to 3 cards per match against opponents
- **Leaderboard**: Server-wide rankings with points (Win=3, Draw=1, Loss=0)

### 🛠️ Admin Tools
- Mass card spawning
- Card distribution to users
- Promo code management
- Logo system management
- Server configuration

## Installation

### Prerequisites

- Python 3.10 or higher
- PostgreSQL 13 or higher
- Discord Bot Token
- API-Football API Key (from https://www.api-football.com/)

### Step 1: Clone and Setup

```bash
cd discord-bot
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Database Setup

Create a PostgreSQL database:

```bash
createdb discord_bot
```

Or using PostgreSQL client:

```sql
CREATE DATABASE discord_bot;
```

### Step 3: Environment Configuration

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=discord_bot
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password_here
API_FOOTBALL_KEY=your_api_football_key_here
PATREON_STORE_LINK=https://patreon.com/yourstore
SPAWN_MESSAGE_MIN=20
SPAWN_MESSAGE_MAX=50
CATCH_TIMEOUT_SECONDS=180
```

### Step 4: Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the bot token to your `.env` file
5. Enable these Privileged Gateway Intents:
   - Server Members Intent
   - Message Content Intent
6. Go to "OAuth2" > "URL Generator"
7. Select scopes: `bot`, `applications.commands`
8. Select bot permissions:
   - Send Messages
   - Send Messages in Threads
   - Embed Links
   - Attach Files
   - Read Message History
   - Add Reactions
   - Use Slash Commands
9. Copy the generated URL and invite the bot to your server

### Step 5: Populate Database with Players

Before running the bot, you should populate the database with player data:

```python
# Create a script populate_db.py
import asyncio
from database.database import AsyncSessionLocal, init_db
from utils.api_football import APIFootball

async def populate():
    await init_db()
    api = APIFootball()
    async with AsyncSessionLocal() as session:
        count = await api.populate_database(session, count=200)
        print(f"Populated database with {count} players")

if __name__ == "__main__":
    asyncio.run(populate())
```

Run it:

```bash
python populate_db.py
```

### Step 6: Run the Bot

```bash
python bot.py
```

## Usage

### For Players

#### Getting Started
1. `/help` - View all available commands
2. `/start` - Create your team
3. `/select lineup` - Choose a formation
4. Catch spawned cards or open packs to build your collection

#### Collection Commands
- `/pack daily` - Open daily pack (24h cooldown)
- `/pack weekly` - Open weekly icon pack (7d cooldown)
- `/pack event` - Open event pack (7d cooldown)
- `/pack premium` - Open premium pack (2d cooldown)
- `/pack booster` - Open booster pack (2d cooldown)
- `/collection` - View your cards
- `/show <player>` - View detailed card info
- `/stats` - View your statistics

#### Team Management
- `/player add <position> <name>` - Add player to team
- `/player remove <position>` - Remove player from position
- `/player swap <pos1> <pos2>` - Swap two players
- `/team` - View your current team
- `/logo add <name>` - Add a logo to your team
- `/logo remove` - Remove your logo

#### Playing Matches
- `/match start <user>` - Challenge another user
- `/select <player>` - Select player for current round
- `/bet <user> <card>` - Bet cards against opponent
- `/leaderboard` - View server rankings

### For Server Owners

- `/configure <channel>` - Set the card spawn channel
- `/toggle_spawning` - Enable/disable card spawning

### For Administrators

- `/admin_spawn` - Spawn 15 cards at once
- `/give_user <user> <card>` - Give card to user
- `/give_club <user> <club>` - Give all cards from a club
- `/give_event <user> <event>` - Give all event cards
- `/give_full <user>` - Give all cards to user
- `/promo_add <code> <reward>` - Create promo code
- `/promo_remove <code>` - Remove promo code
- `/logo_add <name> <bonus> <rarity>` - Add logo to game
- `/logo_remove <name>` - Remove logo from game

## Configuration

### Card Spawn Settings

Adjust in `.env`:
- `SPAWN_MESSAGE_MIN` - Minimum messages before spawn (default: 20)
- `SPAWN_MESSAGE_MAX` - Maximum messages before spawn (default: 50)
- `CATCH_TIMEOUT_SECONDS` - Time to catch card (default: 180)

### Formations and Bonuses

Formations are configured in `config.py`. Each formation has:
- Position layout
- Stat bonuses for specific positions
- Chemistry calculation rules

### Card Types and Events

- **Base Cards**: Regular player cards from packs
- **Icon Cards**: Legendary player cards from weekly packs
- **Event Cards**: Special cards from events (TOTW, TOTS, TOTY, UCL, UEL, International, Special)

## Database Schema

The bot uses PostgreSQL with the following main tables:
- `users` - Discord users and their stats
- `cards` - Player card data from API-Football
- `collections` - User card ownership
- `teams` - User team configurations
- `team_slots` - Player positions in teams
- `logos` - Available team logos
- `matches` - Match history
- `active_matches` - Ongoing matches
- `bets` - Active betting records
- `leaderboard` - Server rankings
- `server_config` - Per-server settings
- `promo_codes` - Promotional codes
- `spawned_cards` - Active card spawns

## API Integration

### API-Football

The bot uses API-Football to fetch real player data:
- Player names, photos, and clubs
- Position mapping to game positions
- Stat calculation from real performance data
- League and nationality information

**Note**: API-Football has rate limits. The free tier allows 100 requests/day. Consider caching data appropriately.

## Development

### Project Structure

```
discord-bot/
├── bot.py                 # Main bot entry point
├── config.py             # Configuration
├── requirements.txt      # Dependencies
├── .env                  # Environment variables (not in git)
├── database/
│   ├── models.py        # SQLAlchemy models
│   └── database.py      # Database connection
├── cogs/
│   ├── help.py          # Help commands
│   ├── team.py          # Team management
│   ├── match.py         # Match system
│   ├── collection.py    # Packs and collection
│   ├── admin.py         # Admin commands
│   └── server_config.py # Server configuration
└── utils/
    ├── api_football.py  # API integration
    ├── card_spawner.py  # Card spawning logic
    ├── match_engine.py  # Match simulation
    ├── formations.py    # Formation system
    └── embeds.py        # Discord embeds
```

### Adding New Features

1. **New Commands**: Add to appropriate cog in `cogs/`
2. **New Card Types**: Update `CardType` enum in `database/models.py`
3. **New Formations**: Add to `FORMATIONS` dict in `config.py`
4. **New Events**: Add to `EVENT_TYPES` list in `config.py`

### Testing

```bash
# Run with debug logging
python bot.py
```

## Troubleshooting

### Database Connection Issues
- Verify PostgreSQL is running
- Check credentials in `.env`
- Ensure database exists

### Bot Not Responding to Commands
- Verify bot has proper permissions in Discord
- Check that intents are enabled in Developer Portal
- Ensure commands are synced (happens automatically on startup)

### Card Spawning Not Working
- Run `/configure` to set spawn channel
- Check that spawning is enabled with `/toggle_spawning`
- Verify bot has permissions to send messages in spawn channel

### API-Football Rate Limits
- Cache player data in database to minimize API calls
- Consider upgrading API plan for production use
- Implement request throttling

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is provided as-is for educational purposes.

## Support

For issues and questions:
- Check the `/help` command in Discord
- Review this README
- Check the code comments for implementation details

## Acknowledgments

- Discord.py for the excellent Discord API wrapper
- API-Football for player data
- PostgreSQL for robust data storage
- The Discord bot community for inspiration

