"""Durable background worker for Phase 8 scheduled job discovery scans."""

import asyncio
import logging
import random
import time
import uuid
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.entities import SavedSearch, ScheduledScanRun
from app.services.scheduler.redis_client import (
    check_redis_availability,
    get_redis_client,
)
from app.services.scheduler.scanner import ScheduledJobScanner

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 300  # 5 minutes distributed lock expiration
DEFAULT_MAX_RETRIES = 3


class ScheduledScanWorker:
    """
    Durable background task worker coordinating scheduled job discovery scans.
    Uses Redis distributed locks for deduplication, bounded retries with exponential
    backoff and jitter, crash recovery, and cancellation controls.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        scanner: ScheduledJobScanner | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_backoff_seconds: float = 1.0,
    ):
        self._redis = redis_client
        self._scanner = scanner or ScheduledJobScanner(redis_client=redis_client)
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds

    def _client(self) -> aioredis.Redis:
        return self._redis if self._redis is not None else get_redis_client()

    async def acquire_scan_lock(self, saved_search_id: int) -> bool:
        """
        Acquire a distributed lock in Redis to prevent simultaneous duplicate scans
        for the same saved search.
        """
        client = self._client()
        lock_key = f"scan:lock:{saved_search_id}"
        try:
            # SET NX with TTL
            acquired = await client.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS)
            return bool(acquired)
        finally:
            if self._redis is None:
                await client.aclose()

    async def release_scan_lock(self, saved_search_id: int) -> None:
        """Release the distributed scan lock."""
        client = self._client()
        lock_key = f"scan:lock:{saved_search_id}"
        try:
            await client.delete(lock_key)
        finally:
            if self._redis is None:
                await client.aclose()

    async def get_due_saved_searches(self) -> list[SavedSearch]:
        """
        Retrieve active, unpaused saved searches that are due for scanning
        (where next_run_at is None or next_run_at <= current time).
        """
        now = datetime.now(UTC)
        async with async_session_factory() as session:
            stmt = (
                select(SavedSearch)
                .where(
                    SavedSearch.is_active.is_(True),
                    (SavedSearch.next_run_at.is_(None)) | (SavedSearch.next_run_at <= now),
                )
                .order_by(SavedSearch.next_run_at.asc())
            )
            return list((await session.execute(stmt)).scalars().all())

    async def request_scan_cancellation(
        self, saved_search_id: int, scan_run_id: int | None = None
    ) -> None:
        """Set a cancellation flag in Redis for an ongoing scan."""
        client = self._client()
        try:
            await client.set(f"scan:cancel:search:{saved_search_id}", "1", ex=120)
            if scan_run_id:
                await client.set(f"scan:cancel:run:{scan_run_id}", "1", ex=120)
        finally:
            if self._redis is None:
                await client.aclose()

    async def execute_search_scan(
        self,
        saved_search_id: int,
        idempotency_key: str | None = None,
    ) -> ScheduledScanRun:
        """
        Execute scheduled scan with distributed locking, bounded retries,
        exponential backoff, and metrics tracking.
        """
        # 1. Verify Redis availability (produces visible error rather than silent data loss)
        await check_redis_availability()

        # 2. Acquire lock to prevent duplicate concurrent runs
        locked = await self.acquire_scan_lock(saved_search_id)
        if not locked:
            logger.info(
                "Scan for saved search %s already running or locked; duplicate skipped.",
                saved_search_id,
            )
            async with async_session_factory() as session:
                existing_run_stmt = (
                    select(ScheduledScanRun)
                    .where(ScheduledScanRun.saved_search_id == saved_search_id)
                    .order_by(ScheduledScanRun.started_at.desc())
                )
                existing = (await session.execute(existing_run_stmt)).scalars().first()
                if existing:
                    return existing

        start_time = time.perf_counter()
        now_dt = datetime.now(UTC)
        sub_key = idempotency_key or f"scan_{saved_search_id}_{int(now_dt.timestamp() * 1000)}_{uuid.uuid4().hex[:6]}"

        async with async_session_factory() as session:
            # 3. Load search configuration
            search = await session.get(SavedSearch, saved_search_id)
            if not search:
                await self.release_scan_lock(saved_search_id)
                raise ValueError(f"Saved search {saved_search_id} not found")

            if not search.is_active:
                await self.release_scan_lock(saved_search_id)
                logger.info(
                    "Saved search %s is paused; execution skipped.", saved_search_id
                )
                return ScheduledScanRun(
                    saved_search_id=saved_search_id,
                    status="cancelled",
                    idempotency_key=sub_key,
                    started_at=now_dt,
                    completed_at=now_dt,
                    error_message="Search is currently paused",
                    run_metadata={},
                )

            # 4. Create and persist ScheduledScanRun record
            scan_run = ScheduledScanRun(
                saved_search_id=saved_search_id,
                status="running",
                idempotency_key=sub_key,
                started_at=now_dt,
                retry_count=0,
                max_retries=self.max_retries,
                run_metadata={"initial_interval_minutes": search.interval_minutes},
            )
            session.add(scan_run)
            await session.commit()
            await session.refresh(scan_run)

            # 5. Execute with bounded retries and exponential backoff + jitter
            attempt = 0
            success = False
            last_error_msg: str | None = None

            while attempt <= self.max_retries:
                attempt += 1
                try:
                    scan_run = await self._scanner.execute_scan(
                        session, search, scan_run
                    )
                    success = True
                    break
                except Exception as exc:
                    last_error_msg = str(exc)
                    scan_run.retry_count = max(0, attempt - 1)
                    logger.warning(
                        "Scan attempt %d/%d for saved search %d failed: %s",
                        attempt,
                        self.max_retries,
                        saved_search_id,
                        exc,
                    )
                    if attempt <= self.max_retries:
                        # Exponential backoff with jitter: base * 2^attempt + jitter
                        backoff_seconds = (self.base_backoff_seconds * (2**attempt)) + random.uniform(0.01, 0.05)
                        await asyncio.sleep(backoff_seconds)
                    else:
                        break

            # 6. Record completion metrics
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            scan_run.duration_ms = duration_ms
            completed_dt = datetime.now(UTC)

            if success and scan_run.status == "completed":
                search.last_run_at = completed_dt
                search.last_success_at = completed_dt
                search.last_error = None
                search.consecutive_failures = 0
                search.total_runs_count += 1
                search.next_run_at = completed_dt + timedelta(
                    minutes=search.interval_minutes
                )
            elif scan_run.status == "cancelled":
                search.last_run_at = completed_dt
                # Keep existing next_run_at or update if active
                if search.is_active:
                    search.next_run_at = completed_dt + timedelta(
                        minutes=search.interval_minutes
                    )
            else:
                scan_run.status = "failed"
                scan_run.error_message = last_error_msg
                scan_run.completed_at = completed_dt
                search.last_run_at = completed_dt
                search.last_failure_at = completed_dt
                search.last_error = last_error_msg
                search.consecutive_failures += 1
                search.total_runs_count += 1
                if search.is_active:
                    search.next_run_at = completed_dt + timedelta(
                        minutes=search.interval_minutes
                    )

            await session.commit()
            await session.refresh(scan_run)
            await self.release_scan_lock(saved_search_id)
            return scan_run

    async def recover_pending_or_stalled_scans(
        self, stale_threshold_seconds: int = 600
    ) -> int:
        """
        Safe crash recovery on worker restart.
        Finds any scans left in 'running' or 'pending' state and reschedules or fails them safely.
        """
        recovered_count = 0
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_threshold_seconds)

        async with async_session_factory() as session:
            stalled_stmt = select(ScheduledScanRun).where(
                ScheduledScanRun.status.in_(["running", "pending"]),
                ScheduledScanRun.started_at <= cutoff,
            )
            stalled_runs = (await session.execute(stalled_stmt)).scalars().all()

            for run in stalled_runs:
                run.status = "failed"
                run.completed_at = datetime.now(UTC)
                run.error_message = (
                    "Scan interrupted by worker restart; recovered and marked failed."
                )
                recovered_count += 1
                await self.release_scan_lock(run.saved_search_id)

                # Ensure search next_run_at is rescheduled
                search = await session.get(SavedSearch, run.saved_search_id)
                if search and search.is_active:
                    search.next_run_at = datetime.now(UTC) + timedelta(
                        minutes=search.interval_minutes
                    )

            await session.commit()

        logger.info(
            "Worker crash recovery concluded: %d stalled scans recovered.",
            recovered_count,
        )
        return recovered_count

    execute_scan = execute_search_scan


scheduled_scan_worker = ScheduledScanWorker()
