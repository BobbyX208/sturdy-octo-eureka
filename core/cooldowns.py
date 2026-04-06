import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import asyncpg

from database.connection import DatabasePool
from core.cache import CacheManager


class CooldownManager:
    
    def __init__(self, db: DatabasePool, cache: CacheManager):
        self.db = db
        self.cache = cache
        self._pending_updates: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def set(self, user_id: int, action: str, seconds: int) -> None:
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            cache_key = f"cooldown:{user_id}:{action}"
            
            await self.cache.set(cache_key, expires_at.isoformat(), ttl=seconds)
            
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO cooldowns (discord_id, action, expires_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (discord_id, action) 
                    DO UPDATE SET expires_at = EXCLUDED.expires_at
                """, user_id, action, expires_at)
                
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Database error setting cooldown: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to set cooldown: {e}")
    
    async def get(self, user_id: int, action: str) -> Optional[datetime]:
        try:
            cache_key = f"cooldown:{user_id}:{action}"
            cached = await self.cache.get(cache_key)
            
            if cached:
                return datetime.fromisoformat(cached)
            
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT expires_at FROM cooldowns
                    WHERE discord_id = $1 AND action = $2 AND expires_at > NOW()
                """, user_id, action)
                
                if row:
                    expires_at = row["expires_at"]
                    ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
                    if ttl > 0:
                        await self.cache.set(cache_key, expires_at.isoformat(), ttl=ttl)
                    return expires_at
                
                return None
                
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Database error getting cooldown: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to get cooldown: {e}")
    
    async def is_active(self, user_id: int, action: str) -> bool:
        try:
            expires_at = await self.get(user_id, action)
            if expires_at:
                return expires_at > datetime.now(timezone.utc)
            return False
            
        except Exception as e:
            raise RuntimeError(f"Failed to check cooldown: {e}")
    
    async def get_remaining(self, user_id: int, action: str) -> int:
        try:
            expires_at = await self.get(user_id, action)
            if expires_at:
                remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
                return max(0, remaining)
            return 0
            
        except Exception as e:
            raise RuntimeError(f"Failed to get remaining cooldown: {e}")
    
    async def clear(self, user_id: int, action: str) -> None:
        try:
            cache_key = f"cooldown:{user_id}:{action}"
            await self.cache.delete(cache_key)
            
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM cooldowns
                    WHERE discord_id = $1 AND action = $2
                """, user_id, action)
                
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Database error clearing cooldown: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to clear cooldown: {e}")
    
    async def clear_all(self, user_id: int) -> None:
        try:
            pattern = f"cooldown:{user_id}:*"
            await self.cache.delete_pattern(pattern)
            
            async with self.db.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM cooldowns WHERE discord_id = $1
                """, user_id)
                
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Database error clearing all cooldowns: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to clear all cooldowns: {e}")
    
    async def cleanup_expired(self) -> int:
        try:
            async with self.db.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM cooldowns
                    WHERE expires_at <= NOW()
                """)
                
                deleted = int(result.split()[-1])
                return deleted
                
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Database error cleaning cooldowns: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to clean cooldowns: {e}")