import redis.asyncio as redis

from src.chatbot_log.chatbot_logger import logger


class RedisManager:
    _instance = None
    _initialized = False

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
            # self.__class__._initialized = True
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

    async def get(self, key: str):
        """Get value from Redis."""
        # if not self.client:
        #     await self.initialize()
        return await self.client.get(key)

    async def setex(self, key: str, time: int, value: str):
        """Set value in Redis with expiration."""
        if not self.client:
            await self.initialize()
        return await self.client.setex(key, time, value)


redis_manager = RedisManager()
