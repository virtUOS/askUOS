import redis.asyncio as redis
from src.chatbot_log.chatbot_logger import logger


class RedisManager:
    _instance = None

    # Redis configuration
    REDIS_MAX_MEMORY = "512mb"
    REDIS_MAX_MEMORY_POLICY = "allkeys-lru"
    REDIS_SAMPLES = 5
    TTL = 24 * 60 * 60  # 24h default TTL

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "client"):
            self.client = None

    async def initialize(self):
        """Initialize Redis connection and settings."""

        try:
            self.client = redis.Redis(
                host="redis",
                port=6379,
                decode_responses=True,
            )
            await self._configure_redis()

        except Exception as e:
            logger.error(f"[REDIS] Failed to initialize: {e}")
            raise

    async def _configure_redis(self):
        """Configure Redis settings."""
        try:
            await self.client.config_set("maxmemory", self.REDIS_MAX_MEMORY)
            await self.client.config_set(
                "maxmemory-policy", self.REDIS_MAX_MEMORY_POLICY
            )
            await self.client.config_set("maxmemory-samples", str(self.REDIS_SAMPLES))

            info = await self.client.info("memory")
            used_memory_mb = int(info["used_memory"]) / 1024 / 1024
            logger.info(
                f"[REDIS] Configured successfully. Memory usage: {used_memory_mb:.2f}MB"
            )
        except Exception as e:
            logger.error(f"[REDIS] Configuration error: {e}")
            raise

    async def is_connected(self):
        """Check if Redis connection is alive."""
        try:
            return self.client is not None and await self.client.ping()
        except Exception:
            return False

    async def ensure_connection(self):
        """Ensure Redis connection is established."""
        if not await self.is_connected():
            await self.initialize()

    async def get(self, key: str):
        """Get value from Redis."""
        await self.ensure_connection()
        return await self.client.get(key)

    async def setex(self, key: str, time: int, value: str):
        """Set value in Redis with expiration."""
        await self.ensure_connection()
        return await self.client.setex(key, time, value)

    async def cleanup(self):
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("[REDIS] Connection closed")


redis_manager = RedisManager()
