"""Distributed rate limit enforcement for job providers in Phase 8."""

import asyncio
import logging
import time
from typing import Any

import redis.asyncio as aioredis

from app.services.scheduler.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Default provider documented rate limits (requests per minute)
PROVIDER_RPM_LIMITS = {
    "greenhouse": 60,
    "indeed": 30,
    "linkedin": 20,
    "manual_import": 120,
    "all": 60,
}


class ProviderRateLimitExceededError(Exception):
    """Raised when a job provider rate limit is currently exhausted."""

    def __init__(self, provider_id: str, retry_after_seconds: float):
        self.provider_id = provider_id
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Provider '{provider_id}' rate limit reached. Retry after {retry_after_seconds:.1f}s."
        )


class ProviderRateLimiter:
    """Redis-backed distributed rate limiter using sliding-window log."""

    def __init__(self, redis_client: aioredis.Redis | None = None):
        self._redis = redis_client

    def _client(self) -> aioredis.Redis:
        return self._redis if self._redis is not None else get_redis_client()

    async def acquire_slot(
        self,
        provider_id: str,
        max_rpm: int | None = None,
        max_wait_seconds: float = 2.0,
    ) -> bool:
        """
        Check rate limit and record a request timestamp.
        If limit is reached within current 60s window, waits if wait <= max_wait_seconds,
        otherwise raises ProviderRateLimitExceededError.
        """
        rpm = max_rpm or PROVIDER_RPM_LIMITS.get(provider_id.lower(), 60)
        client = self._client()
        key = f"rate_limit:provider:{provider_id.lower()}"
        now = time.time()
        window_start = now - 60.0

        try:
            # 1. Clear timestamps older than 60s
            await client.zremrangebyscore(key, 0, window_start)

            # 2. Count requests in current window
            current_count = await client.zcard(key)

            if current_count >= rpm:
                # Find timestamp of earliest request in window to calculate wait
                earliest_entries = await client.zrange(key, 0, 0, withscores=True)
                if earliest_entries:
                    earliest_ts = earliest_entries[0][1]
                    wait_seconds = max(0.1, 60.0 - (now - earliest_ts))
                    if wait_seconds <= max_wait_seconds:
                        logger.info(
                            "Provider %s rate limit near cap; pausing %0.2fs",
                            provider_id,
                            wait_seconds,
                        )
                        await asyncio.sleep(wait_seconds)
                        # Re-clean after wait
                        await client.zremrangebyscore(key, 0, time.time() - 60.0)
                    else:
                        raise ProviderRateLimitExceededError(provider_id, wait_seconds)
                else:
                    raise ProviderRateLimitExceededError(provider_id, 1.0)

            # 3. Add current request timestamp
            member = f"{now}-{time.perf_counter()}"
            await client.zadd(key, {member: now})
            await client.expire(key, 120)
            return True
        finally:
            if self._redis is None:
                await client.aclose()

    def set_provider_limit(self, provider_id: str, rpm: int) -> None:
        """Configure or override RPM limit for a provider."""
        PROVIDER_RPM_LIMITS[provider_id.lower()] = rpm

    async def acquire(self, provider_id: str, max_rpm: int | None = None) -> Any:
        """Non-blocking rate limit check returning acquisition status and retry-after."""
        class AcquireResult:
            def __init__(self, acquired: bool, current_requests: int, retry_after_seconds: float):
                self.acquired = acquired
                self.current_requests = current_requests
                self.retry_after_seconds = retry_after_seconds

        rpm = max_rpm or PROVIDER_RPM_LIMITS.get(provider_id.lower(), 60)
        client = self._client()
        key = f"rate_limit:provider:{provider_id.lower()}"
        now = time.time()
        window_start = now - 60.0
        try:
            await client.zremrangebyscore(key, 0, window_start)
            current_count = await client.zcard(key)
            if current_count >= rpm:
                earliest_entries = await client.zrange(key, 0, 0, withscores=True)
                earliest_ts = earliest_entries[0][1] if earliest_entries else now
                retry_after = max(0.1, 60.0 - (now - earliest_ts))
                return AcquireResult(False, current_count, retry_after)

            member = f"{now}-{time.perf_counter()}"
            await client.zadd(key, {member: now})
            await client.expire(key, 120)
            return AcquireResult(True, current_count + 1, 0.0)
        finally:
            if self._redis is None:
                await client.aclose()

    async def check_and_acquire_strict(self, provider_id: str, max_rpm: int | None = None) -> bool:
        """Acquires a slot or immediately raises ProviderRateLimitExceededError."""
        res = await self.acquire(provider_id, max_rpm=max_rpm)
        if not res.acquired:
            raise ProviderRateLimitExceededError(provider_id, res.retry_after_seconds)
        return True


provider_rate_limiter = ProviderRateLimiter()
