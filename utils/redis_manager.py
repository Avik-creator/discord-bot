import redis.asyncio as redis
import json
import pickle
import logging
from typing import Optional, Dict, Any
from utils.match_engine import MatchState
import config

logger = logging.getLogger('discord_bot')

class RedisManager:
    """Manages Redis connection and match state caching"""
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
    
    async def connect(self):
        """Connect to Redis"""
        try:
            # Build Redis URL from config
            if config.REDIS_PASSWORD:
                redis_url = f"redis://:{config.REDIS_PASSWORD}@{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
            else:
                redis_url = f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
            
            self.redis = await redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False  # We'll handle encoding ourselves
            )
            await self.redis.ping()
            logger.info(f"✅ Connected to Redis at {config.REDIS_HOST}:{config.REDIS_PORT}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            logger.warning("⚠️ Falling back to in-memory storage (match state will be lost on restart)")
            self.redis = None
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")
    
    def _match_key(self, channel_id: int) -> str:
        """Generate Redis key for match state"""
        return f"match:{channel_id}"
    
    def _dropdown_key(self, channel_id: int) -> str:
        """Generate Redis key for dropdown tracking"""
        return f"dropdown:{channel_id}"
    
    async def save_match_state(self, channel_id: int, match_state: MatchState, ttl: Optional[int] = None):
        """
        Save match state to Redis
        TTL: Time to live in seconds (default from config.REDIS_MATCH_TTL)
        """
        if not self.redis:
            return False
        
        try:
            # Use config TTL if not specified
            if ttl is None:
                ttl = config.REDIS_MATCH_TTL
            
            # Serialize match state using pickle (preserves Python objects)
            serialized = pickle.dumps(match_state)
            await self.redis.setex(
                self._match_key(channel_id),
                ttl,
                serialized
            )
            logger.debug(f"Saved match state for channel {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save match state: {e}")
            return False
    
    async def get_match_state(self, channel_id: int) -> Optional[MatchState]:
        """Retrieve match state from Redis"""
        if not self.redis:
            return None
        
        try:
            serialized = await self.redis.get(self._match_key(channel_id))
            if serialized:
                match_state = pickle.loads(serialized)
                logger.debug(f"Retrieved match state for channel {channel_id}")
                return match_state
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve match state: {e}")
            return None
    
    async def delete_match_state(self, channel_id: int):
        """Delete match state from Redis"""
        if not self.redis:
            return False
        
        try:
            await self.redis.delete(self._match_key(channel_id))
            await self.redis.delete(self._dropdown_key(channel_id))
            logger.debug(f"Deleted match state for channel {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete match state: {e}")
            return False
    
    async def save_dropdown_tracking(self, channel_id: int, round_num: int, user_ids: set, ttl: int = 3600):
        """Save dropdown tracking data"""
        if not self.redis:
            return False
        
        try:
            data = {
                "round": round_num,
                "users_sent": list(user_ids)
            }
            await self.redis.setex(
                self._dropdown_key(channel_id),
                ttl,
                json.dumps(data)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save dropdown tracking: {e}")
            return False
    
    async def get_dropdown_tracking(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get dropdown tracking data"""
        if not self.redis:
            return None
        
        try:
            data = await self.redis.get(self._dropdown_key(channel_id))
            if data:
                parsed = json.loads(data)
                parsed["users_sent"] = set(parsed["users_sent"])
                return parsed
            return None
        except Exception as e:
            logger.error(f"Failed to get dropdown tracking: {e}")
            return None
    
    async def check_and_mark_dropdown_sent(self, channel_id: int, round_num: int, user_id: int, ttl: int = 3600) -> bool:
        """
        Check if dropdown already sent to user for this round, and mark as sent if not.
        Returns True if already sent (duplicate), False if new (should send)
        """
        if not self.redis:
            return False
        
        try:
            tracking = await self.get_dropdown_tracking(channel_id)
            
            # Initialize if doesn't exist or wrong round
            if not tracking or tracking["round"] != round_num:
                await self.save_dropdown_tracking(channel_id, round_num, {user_id}, ttl)
                return False  # Not sent yet
            
            # Check if already sent to this user
            if user_id in tracking["users_sent"]:
                return True  # Already sent (duplicate)
            
            # Add user and update
            tracking["users_sent"].add(user_id)
            await self.save_dropdown_tracking(channel_id, round_num, tracking["users_sent"], ttl)
            return False  # Not sent yet
        except Exception as e:
            logger.error(f"Failed to check dropdown tracking: {e}")
            return False

# Global Redis manager instance
redis_manager = RedisManager()
