# Quick Start Guide

Get your Football Card Discord Bot up and running in 5 minutes!

## Prerequisites

Before you start, make sure you have:
- Python 3.10+ installed
- PostgreSQL 13+ installed and running
- A Discord Bot Token ([Get one here](https://discord.com/developers/applications))
- An API-Football API Key ([Get one here](https://www.api-football.com/))

## Setup Steps

### 1. Install Dependencies

```bash
# Run the setup script (macOS/Linux)
./setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Edit the `.env` file with your credentials:

```env
DISCORD_BOT_TOKEN=your_bot_token_here
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=discord_bot
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
API_FOOTBALL_KEY=your_api_key_here
```

### 3. Create Database

```bash
# Using PostgreSQL command line
createdb discord_bot

# Or in psql:
# CREATE DATABASE discord_bot;
```

### 4. Populate Database

```bash
python populate_db.py
```

Follow the prompts to:
- Choose between API-Football or sample data
- Select number of players to fetch (if using API)

### 5. Run the Bot

```bash
# Using the run script (macOS/Linux)
./run.sh

# Or manually:
python bot.py
```

## Discord Bot Setup

### Creating the Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Give it a name (e.g., "Football Card Bot")
4. Go to "Bot" section → Click "Add Bot"
5. Copy the token to your `.env` file

### Enable Intents

In the Bot section, enable:
- ✅ Server Members Intent
- ✅ Message Content Intent

### Generate Invite Link

1. Go to "OAuth2" → "URL Generator"
2. Select scopes:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Select bot permissions:
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Read Message History
   - ✅ Use Slash Commands
4. Copy the generated URL and open it to invite the bot

## First Steps in Discord

Once the bot is online:

1. **Configure spawn channel**:
   ```
   /configure #general
   ```

2. **Create your team**:
   ```
   /start
   /select lineup
   ```

3. **Open your first pack**:
   ```
   /pack daily
   ```

4. **Check help**:
   ```
   /help
   ```

## Troubleshooting

### Bot doesn't respond
- Check bot token is correct
- Verify intents are enabled
- Check bot has permissions in Discord

### Database connection error
- Ensure PostgreSQL is running
- Verify credentials in `.env`
- Check database exists

### Cards not spawning
- Run `/configure` to set spawn channel
- Verify bot can send messages in that channel
- Check spawning is enabled

### API-Football errors
- Verify API key is correct
- Check you haven't exceeded rate limits (100 requests/day on free tier)
- Use sample data option if API is unavailable

## What's Next?

- Read the full [README.md](README.md) for detailed documentation
- Explore all commands with `/help`
- Configure formation bonuses in `config.py`
- Add custom logos with `/logo_add` (admin)
- Create promo codes with `/promo_add` (admin)

## Need Help?

- Check command syntax: `/help <category>`
- Review error messages in console
- Verify database connection
- Check bot permissions in Discord server

---

**🎉 Enjoy your Football Card Bot!**

