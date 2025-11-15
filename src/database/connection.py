"""Database connection management."""

import asyncio
import logging
from typing import Optional
import asyncpg
from asyncpg import Pool

from src.config import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    """Manages the database connection pool."""

    _instance: Optional["DatabasePool"] = None
    _pool: Optional[Pool] = None

    def __new__(cls):
        """Singleton pattern for database pool."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self, database_url: Optional[str] = None) -> None:
        """Initialize the database connection pool."""
        if self._pool is not None:
            return

        url = database_url or settings.database_url
        logger.info("Creating database connection pool...")

        try:
            self._pool = await asyncpg.create_pool(
                url,
                min_size=5,
                max_size=20,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                command_timeout=60
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise

    async def close(self) -> None:
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database connection pool closed")

    @property
    def pool(self) -> Pool:
        """Get the connection pool."""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call initialize() first.")
        return self._pool

    async def execute(self, query: str, *args):
        """Execute a query."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        """Fetch multiple rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        """Fetch a single row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """Fetch a single value."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)


# Global database pool instance
db_pool = DatabasePool()


async def get_db_pool() -> DatabasePool:
    """Get the database pool instance."""
    if db_pool._pool is None:
        await db_pool.initialize()
    return db_pool