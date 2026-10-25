"""Scheduler and notification services for Phase 8."""

from app.services.scheduler.notification_service import (
    NotificationService,
    notification_service,
)
from app.services.scheduler.rate_limiter import (
    ProviderRateLimiter,
    provider_rate_limiter,
)
from app.services.scheduler.redis_client import (
    RedisUnavailableError,
    check_redis_availability,
    get_redis_client,
    reset_redis_client_for_testing,
    set_redis_client_for_testing,
)
from app.services.scheduler.scanner import ScheduledJobScanner
from app.services.scheduler.service import SavedSearchService, saved_search_service
from app.services.scheduler.worker import ScheduledScanWorker, scheduled_scan_worker

__all__ = [
    "RedisUnavailableError",
    "check_redis_availability",
    "get_redis_client",
    "set_redis_client_for_testing",
    "reset_redis_client_for_testing",
    "ProviderRateLimiter",
    "provider_rate_limiter",
    "NotificationService",
    "notification_service",
    "ScheduledJobScanner",
    "ScheduledScanWorker",
    "scheduled_scan_worker",
    "SavedSearchService",
    "saved_search_service",
]
