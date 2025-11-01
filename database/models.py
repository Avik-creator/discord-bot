from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, Float, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.database import Base
import enum

class CardType(enum.Enum):
    BASE = "base"
    ICON = "icon"
    EVENT = "event"

class LogoRarity(enum.Enum):
    COMMON = "common"
    RARE = "rare"
    LEGENDARY = "legendary"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(BigInteger, primary_key=True)  # Discord user ID
    username = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Statistics
    total_games = Column(Integer, default=0)
    total_wins = Column(Integer, default=0)
    total_draws = Column(Integer, default=0)
    total_losses = Column(Integer, default=0)
    cards_collected = Column(Integer, default=0)
    
    # Cooldowns (stored as timestamps)
    daily_pack_cooldown = Column(DateTime(timezone=True), nullable=True)
    weekly_pack_cooldown = Column(DateTime(timezone=True), nullable=True)
    event_pack_cooldown = Column(DateTime(timezone=True), nullable=True)
    premium_pack_cooldown = Column(DateTime(timezone=True), nullable=True)
    booster_pack_cooldown = Column(DateTime(timezone=True), nullable=True)
    vote_cooldown = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    collections = relationship("Collection", back_populates="user", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="user", cascade="all, delete-orphan")
    leaderboard_entries = relationship("Leaderboard", back_populates="user", cascade="all, delete-orphan")
    bets_created = relationship("Bet", foreign_keys="Bet.creator_id", back_populates="creator")
    bets_challenged = relationship("Bet", foreign_keys="Bet.challenged_id", back_populates="challenged")

class Card(Base):
    __tablename__ = 'cards'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_player_id = Column(Integer, nullable=True)  # API-Football player ID
    name = Column(String(255), nullable=False, index=True)
    position = Column(String(10), nullable=False)
    
    # Stats
    overall_rating = Column(Integer, nullable=False)
    attack_stat = Column(Integer, nullable=False)
    defense_stat = Column(Integer, nullable=False)
    
    # Metadata
    club = Column(String(255), nullable=True)
    nation = Column(String(255), nullable=True)
    league = Column(String(255), nullable=True)
    
    # Card type
    card_type = Column(SQLEnum(CardType), default=CardType.BASE)
    event_type = Column(String(50), nullable=True)  # TOTW, TOTS, etc.
    
    # Image URL from API
    photo_url = Column(String(500), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    collections = relationship("Collection", back_populates="card", cascade="all, delete-orphan")
    team_slots = relationship("TeamSlot", back_populates="card")

class Collection(Base):
    __tablename__ = 'collections'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'))
    card_id = Column(Integer, ForeignKey('cards.id', ondelete='CASCADE'))
    
    # Track when card was obtained
    obtained_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="collections")
    card = relationship("Card", back_populates="collections")

class Team(Base):
    __tablename__ = 'teams'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    guild_id = Column(BigInteger, nullable=False)  # Discord server ID
    
    # Formation
    formation = Column(String(50), nullable=True)  # e.g., "433_attack"
    
    # Logo
    logo_id = Column(Integer, ForeignKey('logos.id', ondelete='SET NULL'), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="teams")
    logo = relationship("Logo")
    slots = relationship("TeamSlot", back_populates="team", cascade="all, delete-orphan")

class TeamSlot(Base):
    __tablename__ = 'team_slots'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey('teams.id', ondelete='CASCADE'))
    card_id = Column(Integer, ForeignKey('cards.id', ondelete='CASCADE'))
    position = Column(String(10), nullable=False)  # LW, ST, RW, etc.
    
    # Relationships
    team = relationship("Team", back_populates="slots")
    card = relationship("Card", back_populates="team_slots")

class Logo(Base):
    __tablename__ = 'logos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    rarity = Column(SQLEnum(LogoRarity), default=LogoRarity.COMMON)
    bonus = Column(Integer, default=1)  # +1, +2, or +3 OVR
    image_url = Column(String(500), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Match(Base):
    __tablename__ = 'matches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    
    player1_id = Column(BigInteger, ForeignKey('users.id'))
    player2_id = Column(BigInteger, ForeignKey('users.id'))
    
    # Match result
    player1_score = Column(Integer, default=0)
    player2_score = Column(Integer, default=0)
    winner_id = Column(BigInteger, nullable=True)  # NULL for draw
    
    # Match details stored as JSON
    match_details = Column(JSON, nullable=True)
    
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    player1 = relationship("User", foreign_keys=[player1_id])
    player2 = relationship("User", foreign_keys=[player2_id])

class ActiveMatch(Base):
    __tablename__ = 'active_matches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    channel_id = Column(BigInteger, nullable=False)
    
    player1_id = Column(BigInteger, ForeignKey('users.id'))
    player2_id = Column(BigInteger, ForeignKey('users.id'))
    
    # Current game state
    current_round = Column(Integer, default=1)
    player1_score = Column(Integer, default=0)
    player2_score = Column(Integer, default=0)
    
    # Turn tracking
    current_turn_player = Column(BigInteger, nullable=False)  # Who needs to select
    
    # Game state stored as JSON
    game_state = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    player1 = relationship("User", foreign_keys=[player1_id])
    player2 = relationship("User", foreign_keys=[player2_id])

class Bet(Base):
    __tablename__ = 'bets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    
    creator_id = Column(BigInteger, ForeignKey('users.id'))
    challenged_id = Column(BigInteger, ForeignKey('users.id'))
    
    # Cards being bet (stored as card IDs in JSON array)
    creator_cards = Column(JSON, nullable=False)  # Array of card IDs
    challenged_cards = Column(JSON, nullable=True)  # Array of card IDs
    
    # Status
    accepted = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)
    winner_id = Column(BigInteger, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    creator = relationship("User", foreign_keys=[creator_id], back_populates="bets_created")
    challenged = relationship("User", foreign_keys=[challenged_id], back_populates="bets_challenged")

class Leaderboard(Base):
    __tablename__ = 'leaderboard'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    
    # Points: Win = 3, Draw = 1, Loss = 0
    points = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="leaderboard_entries")

class ServerConfig(Base):
    __tablename__ = 'server_config'
    
    guild_id = Column(BigInteger, primary_key=True)
    spawn_channel_id = Column(BigInteger, nullable=True)
    
    # Message count for spawning
    message_count = Column(Integer, default=0)
    message_threshold = Column(Integer, nullable=True)  # Random between min/max
    
    # Config
    spawn_enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class PromoCode(Base):
    __tablename__ = 'promo_codes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False)
    
    # Reward details stored as JSON
    reward = Column(JSON, nullable=False)  # {"type": "card", "card_id": 123} or {"type": "pack", "pack_type": "premium"}
    
    # Usage limits
    max_uses = Column(Integer, nullable=True)  # NULL = unlimited
    current_uses = Column(Integer, default=0)
    
    # Users who have used this code
    used_by = Column(JSON, default=list)  # Array of user IDs
    
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

class SpawnedCard(Base):
    __tablename__ = 'spawned_cards'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=False)
    channel_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False)
    
    card_id = Column(Integer, ForeignKey('cards.id'))
    
    # Status
    caught = Column(Boolean, default=False)
    caught_by = Column(BigInteger, nullable=True)
    
    spawned_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Relationship
    card = relationship("Card")

