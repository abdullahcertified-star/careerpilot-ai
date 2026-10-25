from collections import defaultdict
from datetime import datetime, timezone
import time
from typing import Dict, List
from fastapi import HTTPException, Request, status

from app.core.config import settings


class InMemoryRateLimiter:
    """Sliding-window rate limiter per client IP address."""

    def __init__(self) -> None:
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        """Check if request count within window is below threshold."""
        now = time.time()
        cutoff = now - window_seconds

        # Clean old timestamps
        timestamps = [ts for ts in self.requests[key] if ts > cutoff]
        self.requests[key] = timestamps

        if len(timestamps) >= max_requests:
            return False

        self.requests[key].append(now)
        return True


rate_limiter = InMemoryRateLimiter()


def rate_limit_auth(request: Request) -> None:
    """Rate limit dependency for authentication endpoints (e.g. login/register)."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    key = f"auth:{client_ip}"
    if not rate_limiter.is_allowed(key, max_requests=settings.RATE_LIMIT_AUTH_PER_MINUTE, window_seconds=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please try again later.",
        )


def rate_limit_general(request: Request) -> None:
    """General rate limit dependency."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    key = f"general:{client_ip}"
    if not rate_limiter.is_allowed(key, max_requests=settings.RATE_LIMIT_GENERAL_PER_MINUTE, window_seconds=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
        )
