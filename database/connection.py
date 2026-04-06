import asyncpg
from asyncpg import Pool, Connection
from typing import Optional, Any
import asyncio
import logging

from config.settings import Config


class DatabasePool:
    
    def __init__(self):
        self.pool: Optional[Pool] = None
        self.logger = logging.getLogger("simcoin.database")
        self.queries = None
    
    @classmethod
    async def connect(cls, dsn: str) -> "DatabasePool":
        instance = cls()
        
        try:
            instance.pool = await asyncpg.create_pool(
                dsn,
                min_size=Config.DATABASE_POOL_SIZE // 2,
                max_size=Config.DATABASE_POOL_SIZE,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                command_timeout=60,
                statement_cache_size=1000
            )
            
            from database.queries import PlayerQueries
            instance.queries = PlayerQueries(instance)
            
            await instance._validate_connection()
            instance.logger.info(f"Database pool created with size {Config.DATABASE_POOL_SIZE}")
            
            return instance
            
        except asyncpg.PostgresError as e:
            instance.logger.error(f"Failed to connect to database: {e}")
            raise
        except Exception as e:
            instance.logger.error(f"Unexpected error during database connection: {e}")
            raise
    
    async def _validate_connection(self) -> None:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
                self.logger.info("Database connection validated")
        except Exception as e:
            self.logger.error(f"Database validation failed: {e}")
            raise
    
    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.logger.info("Database pool closed")
    
    async def execute(self, query: str, *args) -> str:
        try:
            async with self.pool.acquire() as conn:
                return await conn.execute(query, *args)
        except asyncpg.PostgresError as e:
            self.logger.error(f"Execute failed: {e}\nQuery: {query}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during execute: {e}")
            raise
    
    async def fetch(self, query: str, *args) -> list:
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except asyncpg.PostgresError as e:
            self.logger.error(f"Fetch failed: {e}\nQuery: {query}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during fetch: {e}")
            raise
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except asyncpg.PostgresError as e:
            self.logger.error(f"Fetchrow failed: {e}\nQuery: {query}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during fetchrow: {e}")
            raise
    
    async def fetchval(self, query: str, *args) -> Any:
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(query, *args)
        except asyncpg.PostgresError as e:
            self.logger.error(f"Fetchval failed: {e}\nQuery: {query}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during fetchval: {e}")
            raise
    
    async def transaction(self):
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        conn = await self.pool.acquire()
        return conn.transaction()
    
    async def acquire(self) -> Connection:
        return await self.pool.acquire()
    
    async def release(self, conn: Connection) -> None:
        await self.pool.release(conn)
    
    async def health_check(self) -> bool:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False