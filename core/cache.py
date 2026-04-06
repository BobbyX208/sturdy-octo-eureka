import asyncio
import json
from typing import Any, Optional, Dict, List
from datetime import datetime, timezone, timedelta
import hashlib


class CacheManager:
    
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._default_ttl = 3600
    
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._store:
                return None
            
            entry = self._store[key]
            if entry["expires_at"] < datetime.now(timezone.utc):
                del self._store[key]
                return None
            
            return entry["value"]
    
    async def set(self, key: str, value: Any, ttl: int = None) -> None:
        async with self._lock:
            if ttl is None:
                ttl = self._default_ttl
            
            self._store[key] = {
                "value": value,
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl),
                "created_at": datetime.now(timezone.utc)
            }
    
    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        async with self._lock:
            deleted = 0
            keys_to_delete = []
            
            for key in self._store.keys():
                if self._matches_pattern(key, pattern):
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._store[key]
                deleted += 1
            
            return deleted
    
    async def exists(self, key: str) -> bool:
        async with self._lock:
            if key not in self._store:
                return False
            
            entry = self._store[key]
            if entry["expires_at"] < datetime.now(timezone.utc):
                del self._store[key]
                return False
            
            return True
    
    async def incr(self, key: str, amount: int = 1, ttl: int = None) -> int:
        async with self._lock:
            current = await self.get(key)
            
            if current is None:
                current = 0
            
            new_value = current + amount
            await self.set(key, new_value, ttl)
            
            return new_value
    
    async def decr(self, key: str, amount: int = 1, ttl: int = None) -> int:
        async with self._lock:
            current = await self.get(key)
            
            if current is None:
                current = 0
            
            new_value = current - amount
            await self.set(key, new_value, ttl)
            
            return new_value
    
    async def sadd(self, key: str, member: Any, ttl: int = None) -> bool:
        async with self._lock:
            current = await self.get(key)
            
            if current is None:
                current = set()
            
            if not isinstance(current, set):
                current = set(current)
            
            if member in current:
                return False
            
            current.add(member)
            await self.set(key, current, ttl)
            
            return True
    
    async def srem(self, key: str, member: Any) -> bool:
        async with self._lock:
            current = await self.get(key)
            
            if current is None:
                return False
            
            if not isinstance(current, set):
                current = set(current)
            
            if member not in current:
                return False
            
            current.remove(member)
            await self.set(key, current)
            
            return True
    
    async def smembers(self, key: str) -> set:
        current = await self.get(key)
        
        if current is None:
            return set()
        
        if not isinstance(current, set):
            return set(current)
        
        return current
    
    async def hset(self, key: str, field: str, value: Any, ttl: int = None) -> None:
        async with self._lock:
            current = await self.get(key)
            
            if current is None:
                current = {}
            
            if not isinstance(current, dict):
                current = {}
            
            current[field] = value
            await self.set(key, current, ttl)
    
    async def hget(self, key: str, field: str) -> Optional[Any]:
        current = await self.get(key)
        
        if current is None:
            return None
        
        if not isinstance(current, dict):
            return None
        
        return current.get(field)
    
    async def hgetall(self, key: str) -> Dict[str, Any]:
        current = await self.get(key)
        
        if current is None:
            return {}
        
        if not isinstance(current, dict):
            return {}
        
        return current
    
    async def hdel(self, key: str, field: str) -> bool:
        async with self._lock:
            current = await self.get(key)
            
            if current is None:
                return False
            
            if not isinstance(current, dict):
                return False
            
            if field not in current:
                return False
            
            del current[field]
            await self.set(key, current)
            
            return True
    
    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
    
    async def cleanup_expired(self) -> int:
        async with self._lock:
            deleted = 0
            keys_to_delete = []
            
            for key, entry in self._store.items():
                if entry["expires_at"] < datetime.now(timezone.utc):
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._store[key]
                deleted += 1
            
            return deleted
    
    def _matches_pattern(self, key: str, pattern: str) -> bool:
        if "*" in pattern:
            prefix = pattern.replace("*", "")
            return key.startswith(prefix)
        
        if "?" in pattern:
            if len(key) != len(pattern):
                return False
            for k, p in zip(key, pattern):
                if p != "?" and k != p:
                    return False
            return True
        
        return key == pattern
    
    def generate_key(self, *parts) -> str:
        return ":".join(str(part) for part in parts)
    
    def hash_key(self, value: str, prefix: str = "") -> str:
        hash_value = hashlib.md5(value.encode()).hexdigest()
        if prefix:
            return f"{prefix}:{hash_value}"
        return hash_value