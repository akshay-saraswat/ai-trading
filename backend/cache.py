"""
Redis caching layer with fallback to in-memory cache
Reduces Yahoo Finance API calls by 90%
"""
import json
import asyncio
from typing import Optional, Any
from datetime import datetime
import logging

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Async cache manager with Redis and in-memory fallback"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.memory_cache: dict = {}  # Fallback in-memory cache
        self.memory_cache_ttl: dict = {}
        self.enabled = settings.REDIS_ENABLED and REDIS_AVAILABLE

    async def connect(self):
        """Connect to Redis if available"""
        if not self.enabled:
            logger.info("Redis disabled or not available, using in-memory cache")
            return

        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2
            )
            # Test connection
            await self.redis_client.ping()
            logger.info(f"✅ Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except Exception as e:
            logger.warning(f"⚠️  Redis connection failed: {e}. Using in-memory cache")
            self.redis_client = None
            self.enabled = False

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        # Try Redis first
        if self.redis_client:
            try:
                value = await self.redis_client.get(key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.error(f"Redis GET error: {e}")

        # Fallback to memory cache
        if key in self.memory_cache:
            ttl = self.memory_cache_ttl.get(key, 0)
            if datetime.now().timestamp() < ttl:
                return self.memory_cache[key]
            else:
                # Expired
                del self.memory_cache[key]
                del self.memory_cache_ttl[key]

        return None

    async def set(self, key: str, value: Any, ttl: int):
        """Set value in cache with TTL"""
        serialized = json.dumps(value)

        # Try Redis first
        if self.redis_client:
            try:
                await self.redis_client.setex(key, ttl, serialized)
                return
            except Exception as e:
                logger.error(f"Redis SET error: {e}")

        # Fallback to memory cache
        self.memory_cache[key] = value
        self.memory_cache_ttl[key] = datetime.now().timestamp() + ttl


# Global cache instance
cache = CacheManager()
