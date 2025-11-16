# MatchDex Bot - Server Setup Guide

This guide will walk you through setting up and running the MatchDex Discord bot on your server.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Database Setup](#database-setup)
5. [Running the Bot](#running-the-bot)
6. [API Server (Optional)](#api-server-optional)
7. [Troubleshooting](#troubleshooting)
8. [Production Deployment](#production-deployment)

---

## Prerequisites

### Required Software
- **Python 3.8+** (Python 3.10+ recommended)
- **PostgreSQL 12+** (local or cloud database like Neon, Supabase, etc.)
- **Git** (for cloning the repository)

### Required Accounts & API Keys
- **Discord Bot Token** - Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
- **PostgreSQL Database** - Local installation or cloud database URL
- **API-Football Key** (Optional) - For syncing real player data from [API-Football](https://www.api-football.com/)

### Discord Bot Setup
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section
4. Click "Add Bot" and confirm
5. Under "Privileged Gateway Intents", enable:
   - ✅ **Message Content Intent** (Required for card spawning)
   - ✅ **Server Members Intent** (Required for member features)
6. Copy the bot token (you'll need this for `.env` file)
7. Go to "OAuth2" → "URL Generator"
8. Select scopes: `bot` and `applications.commands`
9. Select bot permissions:
   - Send Messages
   - Embed Links
   - Attach Files
   - Read Message History
   - Use Slash Commands
   - Manage Messages (optional, for cleanup)
10. Copy the generated URL and use it to invite the bot to your server

---

## Installation

### Step 1: Clone or Download the Repository
```bash
# If using Git
git clone <repository-url>
cd discord-bot

# Or download and extract the ZIP file
```

### Step 2: Create Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
# Upgrade pip
pip install --upgrade pip

# Install all required packages
pip install -r requirements.txt
```

**Or use the automated setup script:**
```bash
# Make script executable (macOS/Linux)
chmod +x setup.sh

# Run setup script
./setup.sh
```

---

## Configuration

### Step 1: Create `.env` File
Create a `.env` file in the root directory of the project:

```bash
# Copy from example (if exists)
cp .env.example .env

# Or create manually
touch .env
```

### Step 2: Configure Environment Variables
Edit the `.env` file with your credentials:

```env
# Discord Configuration (REQUIRED)
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_PUBLIC_KEY=your_public_key_here

# Database Configuration (REQUIRED)
# Option 1: Use full DATABASE_URL (recommended for cloud databases)
DATABASE_URL=postgresql://user:password@host:port/database

# Option 2: Use individual components (for local databases)
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# POSTGRES_DB=discord_bot
# POSTGRES_USER=postgres
# POSTGRES_PASSWORD=your_password

# API Configuration (OPTIONAL - for syncing player data)
API_FOOTBALL_KEY=your_api_football_key_here

# Bot Configuration (OPTIONAL - defaults provided)
PATREON_STORE_LINK=https://patreon.com/yourstore
SPAWN_MESSAGE_MIN=20
SPAWN_MESSAGE_MAX=50
CATCH_TIMEOUT_SECONDS=180

# API Server Configuration (OPTIONAL)
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8000
```

### Database URL Examples

**Local PostgreSQL:**
```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/discord_bot
```

**Neon (Cloud PostgreSQL):**
```env
DATABASE_URL=postgresql://user:password@ep-xxx-xxx.us-east-2.aws.neon.tech/dbname
```

**Supabase:**
```env
DATABASE_URL=postgresql://postgres:password@db.xxx.supabase.co:5432/postgres
```

---

## Database Setup

### Step 1: Create Database
If using local PostgreSQL:

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE discord_bot;

# Exit psql
\q
```

### Step 2: Initialize Database Tables
The bot will automatically create tables on first run, but you can also run:

```bash
# Activate virtual environment first
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Run database initialization
python -c "from database.database import init_db; import asyncio; asyncio.run(init_db())"
```

### Step 3: Populate Card Data (Optional)
If you have card data to import:

```bash
python populate_db.py
```

---

## Running the Bot

### Method 1: Using the Run Script (Recommended)
```bash
# Make script executable (macOS/Linux)
chmod +x run.sh

# Run the bot
./run.sh
```

### Method 2: Manual Run
```bash
# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Run the bot
python bot.py
```

### Method 3: Using Python Directly
```bash
# With virtual environment activated
python3 bot.py
```

### Expected Output
When the bot starts successfully, you should see:
```
INFO - Initializing database...
INFO - Loading cogs...
INFO - Cog 'cogs.help' loaded successfully
INFO - Cog 'cogs.collection' loaded successfully
...
INFO - Bot is ready! Logged in as YourBotName#1234
```

---

## API Server (Optional)

The bot includes an optional FastAPI server for external integrations.

### Running API Server
```bash
# Activate virtual environment
source venv/bin/activate

# Run API server
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

### API Server Endpoints
- `GET /health` - Health check
- `GET /api/users/{user_id}` - Get user information
- `GET /api/users/{user_id}/collection` - Get user's card collection
- `GET /api/users/{user_id}/team` - Get user's team

See `API_DOCUMENTATION.md` for full API documentation.

---

## Troubleshooting

### Common Issues

#### 1. Bot Not Starting - Missing Token
**Error:** `KeyError: 'DISCORD_BOT_TOKEN'` or `NoneType has no attribute...`

**Solution:**
- Ensure `.env` file exists in the root directory
- Check that `DISCORD_BOT_TOKEN` is set correctly
- Verify there are no extra spaces or quotes around the token

#### 2. Database Connection Failed
**Error:** `asyncpg.exceptions.InvalidPasswordError` or connection timeout

**Solution:**
- Verify database credentials in `.env`
- Check if PostgreSQL is running: `pg_isready` or `systemctl status postgresql`
- For cloud databases, ensure IP whitelist allows your connection
- Check firewall settings

#### 3. Privileged Intents Not Enabled
**Error:** `Missing Access` or card spawning not working

**Solution:**
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your bot application
3. Go to "Bot" section
4. Enable "Message Content Intent" and "Server Members Intent"
5. Restart the bot

#### 4. Module Not Found Errors
**Error:** `ModuleNotFoundError: No module named 'discord'`

**Solution:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

#### 5. Database Migration Errors
**Error:** `Column already exists` or migration failures

**Solution:**
- The bot handles migrations automatically
- If issues persist, check database permissions
- For fresh start, you can reset the database (see below)

#### 6. Card Spawning Not Working
**Error:** Cards not appearing in channels

**Solution:**
- Verify "Message Content Intent" is enabled
- Check bot has "Send Messages" permission in the channel
- Ensure `SPAWN_MESSAGE_MIN` and `SPAWN_MESSAGE_MAX` are set correctly
- Check bot logs for errors

### Reset Database (Use with Caution)
⚠️ **Warning:** This will delete all data!

```bash
# Activate virtual environment
source venv/bin/activate

# Run reset script
python reset_db.py
```

### Check Bot Logs
The bot logs important information. Check the console output for:
- Database connection status
- Cog loading status
- Error messages
- Card spawning events

---

## Production Deployment

### Using systemd (Linux)

Create a service file `/etc/systemd/system/matchdex-bot.service`:

```ini
[Unit]
Description=MatchDex Discord Bot
After=network.target postgresql.service

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/discord-bot
Environment="PATH=/path/to/discord-bot/venv/bin"
ExecStart=/path/to/discord-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl enable matchdex-bot
sudo systemctl start matchdex-bot
sudo systemctl status matchdex-bot
```

### Using PM2 (Node.js Process Manager)

```bash
# Install PM2
npm install -g pm2

# Start bot with PM2
pm2 start bot.py --name matchdex-bot --interpreter python3

# Save PM2 configuration
pm2 save

# Setup PM2 to start on boot
pm2 startup
```

### Using Docker (Optional)

Create `Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

Build and run:
```bash
docker build -t matchdex-bot .
docker run -d --name matchdex-bot --env-file .env matchdex-bot
```

### Environment Variables in Production
- Use secure environment variable management
- Never commit `.env` file to version control
- Use secrets management (AWS Secrets Manager, HashiCorp Vault, etc.)
- Rotate tokens regularly

### Monitoring
- Set up logging to file: Modify `bot.py` to add file handler
- Use process managers (PM2, systemd) for automatic restarts
- Monitor database connections and bot uptime
- Set up alerts for critical errors

---

## Quick Start Checklist

- [ ] Python 3.8+ installed
- [ ] PostgreSQL database set up (local or cloud)
- [ ] Discord bot created and token obtained
- [ ] Privileged intents enabled in Discord Developer Portal
- [ ] Bot invited to server with required permissions
- [ ] Repository cloned/downloaded
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with all required variables
- [ ] Database connection tested
- [ ] Bot started successfully
- [ ] Bot appears online in Discord
- [ ] Test commands work (`/help`)

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review bot logs for error messages
3. Verify all configuration steps are completed
4. Check Discord API status: https://discordstatus.com/

---

## Additional Resources

- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [API-Football Documentation](https://www.api-football.com/documentation-v3)

---

**Last Updated:** 2024
**Version:** 1.0

