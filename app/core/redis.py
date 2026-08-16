from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    """Close the shared Redis connection pool."""
    await redis_client.aclose()


def get_redis() -> Redis:
    """FastAPI dependency returning the shared Redis client."""
    return redis_client
