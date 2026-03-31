"""
Standalone async Redis client for MCP tools.

Provides a thin caching layer that is independent of the main application's
redis_pool so that the MCP server can be deployed without the full askUOS
application stack.

Usage
-----
    from src.mcp_tools.redis_cache import get_redis_client, cache_get, cache_set

    client = await get_redis_client()
    await cache_set(client, "my-key", "my-value", ttl=3600)
    value = await cache_get(client, "my-key")  # returns None on cache miss
"""

import asyncio
import logging
from typing import Optional

import redis.asyncio as aioredis

from src.mcp_tools.config import REDIS_HOST, REDIS_PORT, REDIS_TTL

logger = logging.getLogger(__name__)

# Module-level singleton pool so every coroutine in the same process shares
# a single connection pool.
_pool: Optional[aioredis.BlockingConnectionPool] = None
_pool_lock: asyncio.Lock = asyncio.Lock()


async def _get_pool() -> aioredis.BlockingConnectionPool:
    """Lazily initialise the shared connection pool."""
    global _pool

    async with _pool_lock:
        if _pool is None:
            _pool = aioredis.BlockingConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                timeout=15,
                decode_responses=True,
                max_connections=20,
            )
            logger.info(
                "[MCP-REDIS] Connection pool initialised (%s:%s)", REDIS_HOST, REDIS_PORT
            )

    return _pool


async def get_redis_client() -> aioredis.Redis:
    """Return an async Redis client backed by the shared pool."""
    pool = await _get_pool()
    return aioredis.Redis(connection_pool=pool)


async def cache_get(client: aioredis.Redis, key: str) -> Optional[str]:
    """
    Retrieve *key* from the cache.

    Returns the cached string value, or ``None`` on a cache miss or error.
    """
    try:
        value = await client.get(key)
        if value is not None:
            logger.debug("[MCP-REDIS] Cache HIT – key=%s", key)
        else:
            logger.debug("[MCP-REDIS] Cache MISS – key=%s", key)
        return value
    except Exception as exc:
        logger.error("[MCP-REDIS] Error reading key=%s: %s", key, exc)
        return None


async def cache_set(
    client: aioredis.Redis,
    key: str,
    value: str,
    ttl: int = REDIS_TTL,
) -> None:
    """
    Store *value* under *key* with the given TTL (seconds).

    Errors are logged and swallowed so that a Redis failure never breaks the
    main tool logic.
    """
    try:
        await client.setex(key, ttl, value)
        logger.debug("[MCP-REDIS] Cached key=%s (ttl=%ds)", key, ttl)
    except Exception as exc:
        logger.error("[MCP-REDIS] Error writing key=%s: %s", key, exc)
