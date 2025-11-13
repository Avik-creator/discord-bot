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

# API Server Configuration
API_SERVER_HOST = os.getenv('API_SERVER_HOST', '0.0.0.0')
API_SERVER_PORT = int(os.getenv('API_SERVER_PORT', '8000'))

# Game Constants
VALID_POSITIONS = [
    'GK',
    'LB', 'LWB', 'LCB', 'CB', 'RCB', 'RWB', 'RB',
    'LDM', 'CDM', 'RDM',
    'LM', 'LCM', 'CM', 'RCM', 'RM',
    'LAM', 'CAM', 'RAM',
    'LW', 'ST', 'CF', 'RW'
]

_ROW_X_POSITIONS = {
    1: [5],
    2: [4, 6],
    3: [3, 5, 7],
    4: [2, 4, 6, 8],
    5: [1, 3, 5, 7, 9],
}


def _build_positions(rows):
    positions = {'GK': (5, 10)}
    for row in rows:
        names = row['positions']
        y = row['y']
        x_positions = row.get('x_positions') or _ROW_X_POSITIONS.get(len(names))
        if not x_positions or len(x_positions) != len(names):
            raise ValueError(f"Invalid x_positions for row {names}")
        for name, x in zip(names, x_positions):
            positions[name] = (x, y)
    return positions


def _formation(name, rows, bonuses=None):
    return {
        'name': name,
        'positions': _build_positions(rows),
        'bonuses': bonuses or {}
    }

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

FORMATIONS.update({
    '442_flat': _formation(
        '4-4-2 Flat',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LM', 'LCM', 'RCM', 'RM'], 'y': 6},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '343_flat': _formation(
        '3-4-3 Flat',
        [
            {'positions': ['LCB', 'CB', 'RCB'], 'y': 8},
            {'positions': ['LWB', 'LDM', 'RDM', 'RWB'], 'y': 7, 'x_positions': [2, 4, 6, 8]},
            {'positions': ['LCM', 'RCM'], 'y': 5, 'x_positions': [4, 6]},
            {'positions': ['LW', 'ST', 'RW'], 'y': 3, 'x_positions': [2, 5, 8]},
        ]
    ),
    '4231_narrow': _formation(
        '4-2-3-1 Narrow',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LDM', 'RDM'], 'y': 7, 'x_positions': [4, 6]},
            {'positions': ['LAM', 'CAM', 'RAM'], 'y': 5, 'x_positions': [3, 5, 7]},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '4141': _formation(
        '4-1-4-1',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['CDM'], 'y': 7},
            {'positions': ['LM', 'LCM', 'RCM', 'RM'], 'y': 6},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '5221': _formation(
        '5-2-2-1',
        [
            {'positions': ['LB', 'LCB', 'CB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LCM', 'RCM'], 'y': 6, 'x_positions': [4, 6]},
            {'positions': ['LAM', 'RAM'], 'y': 4, 'x_positions': [3, 7]},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '41212_narrow': _formation(
        '4-1-2-1-2 Narrow',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['CDM'], 'y': 7},
            {'positions': ['LCM', 'RCM'], 'y': 6, 'x_positions': [4, 6]},
            {'positions': ['CAM'], 'y': 5},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '451': _formation(
        '4-5-1',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LM', 'LCM', 'CAM', 'RCM', 'RM'], 'y': 6},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '4222': _formation(
        '4-2-2-2',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LDM', 'RDM'], 'y': 7, 'x_positions': [4, 6]},
            {'positions': ['LAM', 'RAM'], 'y': 5, 'x_positions': [3, 7]},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '433': _formation(
        '4-3-3',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LCM', 'CM', 'RCM'], 'y': 6},
            {'positions': ['LW', 'ST', 'RW'], 'y': 3, 'x_positions': [2, 5, 8]},
        ]
    ),
    '541_holding': _formation(
        '5-4-1 Holding',
        [
            {'positions': ['LB', 'LCB', 'CB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['CDM'], 'y': 7},
            {'positions': ['LM', 'LCM', 'RCM', 'RM'], 'y': 6},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '5212': _formation(
        '5-2-1-2',
        [
            {'positions': ['LB', 'LCB', 'CB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LCM', 'RCM'], 'y': 6, 'x_positions': [4, 6]},
            {'positions': ['CAM'], 'y': 5},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '451_flat': _formation(
        '4-5-1 Flat',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LM', 'LCM', 'CDM', 'RCM', 'RM'], 'y': 6},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '3511': _formation(
        '3-5-1-1',
        [
            {'positions': ['LCB', 'CB', 'RCB'], 'y': 8},
            {'positions': ['LWB', 'LDM', 'CDM', 'RDM', 'RWB'], 'y': 7},
            {'positions': ['CAM'], 'y': 5},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '41212_wide': _formation(
        '4-1-2-1-2 Wide',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['CDM'], 'y': 7},
            {'positions': ['LM', 'RM'], 'y': 6, 'x_positions': [2, 8]},
            {'positions': ['CAM'], 'y': 5},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '433_holding': _formation(
        '4-3-3 Holding',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['CDM'], 'y': 7},
            {'positions': ['LCM', 'RCM'], 'y': 6, 'x_positions': [4, 6]},
            {'positions': ['LW', 'ST', 'RW'], 'y': 3, 'x_positions': [2, 5, 8]},
        ]
    ),
    '352': _formation(
        '3-5-2',
        [
            {'positions': ['LCB', 'CB', 'RCB'], 'y': 8},
            {'positions': ['LWB', 'LDM', 'CAM', 'RDM', 'RWB'], 'y': 7},
            {'positions': ['ST', 'CF'], 'y': 3, 'x_positions': [4, 6]},
        ]
    ),
    '433_defend': _formation(
        '4-3-3 Defend',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LDM', 'CDM', 'RDM'], 'y': 7},
            {'positions': ['LW', 'ST', 'RW'], 'y': 3, 'x_positions': [2, 5, 8]},
        ]
    ),
    '532': _formation(
        '5-3-2',
        [
            {'positions': ['LB', 'LCB', 'CB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LCM', 'CM', 'RCM'], 'y': 6},
            {'positions': ['ST', 'CF'], 'y': 3, 'x_positions': [4, 6]},
        ]
    ),
    '4231_wide': _formation(
        '4-2-3-1 Wide',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LDM', 'RDM'], 'y': 7, 'x_positions': [4, 6]},
            {'positions': ['LM', 'CAM', 'RM'], 'y': 5, 'x_positions': [2, 5, 8]},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '442_holding': _formation(
        '4-4-2 Holding',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LDM', 'RDM'], 'y': 7, 'x_positions': [4, 6]},
            {'positions': ['LCM', 'RCM'], 'y': 6, 'x_positions': [4, 6]},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '4312': _formation(
        '4-3-1-2',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LCM', 'CM', 'RCM'], 'y': 6},
            {'positions': ['CAM'], 'y': 5},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '4411_flat': _formation(
        '4-4-1-1 Flat',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LM', 'LCM', 'RCM', 'RM'], 'y': 6},
            {'positions': ['CF'], 'y': 4},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '3412': _formation(
        '3-4-1-2',
        [
            {'positions': ['LCB', 'CB', 'RCB'], 'y': 8},
            {'positions': ['LWB', 'LDM', 'RDM', 'RWB'], 'y': 7, 'x_positions': [2, 4, 6, 8]},
            {'positions': ['CAM'], 'y': 5},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '433_false9': _formation(
        '4-3-3 False 9',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LCM', 'CDM', 'RCM'], 'y': 6},
            {'positions': ['CF'], 'y': 4},
            {'positions': ['LW', 'RW'], 'y': 3, 'x_positions': [2, 8]},
        ]
    ),
    '4213': _formation(
        '4-2-1-3',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LDM', 'RDM'], 'y': 7, 'x_positions': [4, 6]},
            {'positions': ['CAM'], 'y': 5},
            {'positions': ['LW', 'ST', 'RW'], 'y': 3, 'x_positions': [2, 5, 8]},
        ]
    ),
    '4132': _formation(
        '4-1-3-2',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['CDM'], 'y': 7},
            {'positions': ['LCM', 'CM', 'RCM'], 'y': 6},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '4321': _formation(
        '4-3-2-1',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LCM', 'CM', 'RCM'], 'y': 6},
            {'positions': ['LAM', 'RAM'], 'y': 5, 'x_positions': [3, 7]},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '4411_attack': _formation(
        '4-4-1-1 Attack',
        [
            {'positions': ['LB', 'LCB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LM', 'LCM', 'RCM', 'RM'], 'y': 6},
            {'positions': ['CAM'], 'y': 4},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '3142': _formation(
        '3-1-4-2',
        [
            {'positions': ['LCB', 'CB', 'RCB'], 'y': 8},
            {'positions': ['CDM'], 'y': 7},
            {'positions': ['LM', 'LCM', 'RCM', 'RM'], 'y': 6},
            {'positions': ['ST', 'CF'], 'y': 2, 'x_positions': [4, 6]},
        ]
    ),
    '3421': _formation(
        '3-4-2-1',
        [
            {'positions': ['LCB', 'CB', 'RCB'], 'y': 8},
            {'positions': ['LWB', 'LDM', 'RDM', 'RWB'], 'y': 7, 'x_positions': [2, 4, 6, 8]},
            {'positions': ['LAM', 'RAM'], 'y': 5, 'x_positions': [3, 7]},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
    '541_defend': _formation(
        '5-4-1 Defend',
        [
            {'positions': ['LB', 'LCB', 'CB', 'RCB', 'RB'], 'y': 8},
            {'positions': ['LDM', 'CDM', 'RDM'], 'y': 7},
            {'positions': ['LM', 'RM'], 'y': 6, 'x_positions': [2, 8]},
            {'positions': ['ST'], 'y': 2},
        ]
    ),
})

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

