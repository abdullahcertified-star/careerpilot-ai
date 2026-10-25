"""Redis connection client and availability checking for Phase 8 scheduled tasks."""

import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_test_redis_client: aioredis.Redis | None = None


class RedisUnavailableError(Exception):
    """Raised when Redis background queue/worker service is unreachable."""

    def __init__(
        self,
        message: str = (
            "Redis service is unreachable at configured REDIS_URL. "
            "Scheduled background task workers and scan queues require an operational Redis instance."
        ),
    ):
        super().__init__(message)


def set_redis_client_for_testing(client: aioredis.Redis | None) -> None:
    """Inject a test Redis client (e.g. fakeredis) for test isolation."""
    global _test_redis_client
    _test_redis_client = client


def reset_redis_client_for_testing() -> None:
    """Reset test Redis client override."""
    global _test_redis_client
    _test_redis_client = None


def get_redis_client() -> aioredis.Redis:
    """Retrieve async Redis client instance."""
    if _test_redis_client is not None:
        return _test_redis_client
    return aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )


async def check_redis_availability() -> bool:
    """
    Check if Redis is reachable.
    Raises RedisUnavailableError if unreachable to produce a visible error instead of silent data loss.
    """
    client = get_redis_client()
    try:
        pong = await client.ping()
        if pong is True or pong == "PONG":
            return True
        raise RedisUnavailableError(f"Unexpected Redis ping response: {pong}")
    except (
        aioredis.ConnectionError,
        aioredis.TimeoutError,
        ConnectionRefusedError,
        OSError,
    ) as exc:
        raise RedisUnavailableError(
            f"Redis service is unreachable at {settings.REDIS_URL}: {exc}. "
            "Scheduled scans and background queue operations require an active Redis service."
        ) from exc
    finally:
        if _test_redis_client is None:
            await client.aclose()
