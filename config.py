import os
from dotenv import load_dotenv

load_dotenv()

# Discord Configuration
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Database Configuration
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'discord_bot')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# API Configuration
API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')
API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"

# Bot Configuration
PATREON_STORE_LINK = os.getenv('PATREON_STORE_LINK', 'https://patreon.com/yourstore')
SPAWN_MESSAGE_MIN = int(os.getenv('SPAWN_MESSAGE_MIN', '20'))
SPAWN_MESSAGE_MAX = int(os.getenv('SPAWN_MESSAGE_MAX', '50'))
CATCH_TIMEOUT_SECONDS = int(os.getenv('CATCH_TIMEOUT_SECONDS', '180'))

# Game Constants
VALID_POSITIONS = ['LW', 'ST', 'RW', 'CAM', 'LCM', 'RCM', 'CDM', 'LB', 'LCB', 'RCB', 'RB', 'GK']

FORMATIONS = {
    '433_attack': {
        'name': '4-3-3 Attack',
        'positions': {
            'GK': (5, 10),
            'LB': (2, 8), 'LCB': (4, 8), 'RCB': (6, 8), 'RB': (8, 8),
            'LCM': (3, 5), 'RCM': (7, 5), 'CDM': (5, 6),
            'LW': (2, 2), 'ST': (5, 1), 'RW': (8, 2)
        },
        'bonuses': {'LW': {'attack': 2}, 'ST': {'attack': 2}, 'RW': {'attack': 2}}
    },
    '433_defense': {
        'name': '4-3-3 Defense',
        'positions': {
            'GK': (5, 10),
            'LB': (2, 8), 'LCB': (4, 8), 'RCB': (6, 8), 'RB': (8, 8),
            'LCM': (3, 6), 'RCM': (7, 6), 'CDM': (5, 7),
            'LW': (2, 2), 'ST': (5, 1), 'RW': (8, 2)
        },
        'bonuses': {'LCM': {'defense': 2}, 'RCM': {'defense': 2}, 'CDM': {'defense': 2}, 
                    'LB': {'defense': 1}, 'LCB': {'defense': 1}, 'RCB': {'defense': 1}, 'RB': {'defense': 1}}
    },
    '442_diamond': {
        'name': '4-4-2 Diamond',
        'positions': {
            'GK': (5, 10),
            'LB': (2, 8), 'LCB': (4, 8), 'RCB': (6, 8), 'RB': (8, 8),
            'LCM': (3, 6), 'RCM': (7, 6), 'CDM': (5, 7), 'CAM': (5, 4),
            'LW': (3, 1), 'RW': (7, 1)
        },
        'bonuses': {pos: {'attack': 1, 'defense': 1} for pos in VALID_POSITIONS}
    },
    '424': {
        'name': '4-2-4',
        'positions': {
            'GK': (5, 10),
            'LB': (2, 8), 'LCB': (4, 8), 'RCB': (6, 8), 'RB': (8, 8),
            'LCM': (3, 6), 'RCM': (7, 6),
            'LW': (2, 2), 'ST': (5, 1), 'RW': (8, 2), 'CAM': (5, 3)
        },
        'bonuses': {'LW': {'attack': 3}, 'ST': {'attack': 3}, 'RW': {'attack': 3}, 'CAM': {'attack': 3},
                    'LCM': {'defense': -1}, 'RCM': {'defense': -1}}
    },
    '343_diamond': {
        'name': '3-4-3 Diamond',
        'positions': {
            'GK': (5, 10),
            'LCB': (3, 8), 'RCB': (7, 8), 'CDM': (5, 8),
            'LCM': (2, 5), 'RCM': (8, 5), 'CAM': (5, 4), 'LB': (3, 6), 'RB': (7, 6),
            'LW': (2, 2), 'ST': (5, 1), 'RW': (8, 2)
        },
        'bonuses': {'LCM': {'attack': 2, 'defense': 1}, 'RCM': {'attack': 2, 'defense': 1}, 
                    'CAM': {'attack': 2}, 'LB': {'defense': 1}, 'RB': {'defense': 1}}
    }
}

# Cooldown times in seconds
COOLDOWNS = {
    'daily_pack': 86400,      # 24 hours
    'weekly_pack': 604800,     # 7 days
    'event_pack': 604800,      # 7 days
    'premium_pack': 172800,    # 2 days
    'booster_pack': 172800,    # 2 days
    'vote': 86400              # 24 hours
}

# Rarity definitions
LOGO_RARITIES = {
    'common': 1,
    'rare': 2,
    'legendary': 3
}

# Card types
CARD_TYPES = ['base', 'icon', 'event']

# Event types
EVENT_TYPES = ['TOTW', 'TOTS', 'TOTY', 'UCL', 'UEL', 'International', 'Special']

