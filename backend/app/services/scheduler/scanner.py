"""Job scanner engine for Phase 8 scheduled searches."""

import logging
from datetime import UTC, datetime

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.job_providers import registry
from app.models.entities import (
    JobApplication,
    JobPosting,
    SavedSearch,
    ScheduledScanRun,
)
from app.schemas.job import JobSearchQuery, NormalizedJob
from app.services.job_service import JobService
from app.services.matching_service import MatchingService
from app.services.scheduler.notification_service import notification_service
from app.services.scheduler.rate_limiter import provider_rate_limiter
from app.services.scheduler.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ScanCancelledError(Exception):
    """Raised when an ongoing scan is cancelled by user request."""


class ScheduledJobScanner:
    """Executes a single scan run for a saved search, evaluating matches and notifying candidate."""

    def __init__(self, redis_client: aioredis.Redis | None = None):
        self._redis = redis_client

    def _client(self) -> aioredis.Redis:
        return self._redis if self._redis is not None else get_redis_client()

    async def is_cancelled(self, scan_run_id: int, search_id: int) -> bool:
        """Check if scan cancellation was requested in Redis."""
        client = self._client()
        try:
            flag_run = await client.get(f"scan:cancel:run:{scan_run_id}")
            flag_search = await client.get(f"scan:cancel:search:{search_id}")
            return bool(flag_run or flag_search)
        finally:
            if self._redis is None:
                await client.aclose()

    async def execute_scan(
        self,
        session: AsyncSession,
        saved_search: SavedSearch,
        scan_run: ScheduledScanRun,
    ) -> ScheduledScanRun:
        """
        Execute discovery query for saved search.
        Deduplicates listings, scores candidate matching, and dispatches in-app notifications.
        NEVER invokes application submission.
        """
        user_id = saved_search.user_id
        search_query_str = (
            " ".join(filter(None, [saved_search.role, *saved_search.keywords]))
            or saved_search.name
        )

        # 1. Check for early cancellation
        if await self.is_cancelled(scan_run.id, saved_search.id):
            scan_run.status = "cancelled"
            scan_run.error_message = (
                "Scan cancelled by user request before provider query."
            )
            scan_run.completed_at = datetime.now(UTC)
            return scan_run

        # 2. Acquire provider rate limit slot
        target_provider = saved_search.provider_id or "greenhouse"
        provider_name = target_provider if target_provider != "all" else "greenhouse"
        await provider_rate_limiter.acquire_slot(provider_name)

        # 3. Discover jobs from registered provider
        discovered_jobs: list[NormalizedJob] = []
        try:
            query_obj = JobSearchQuery(
                query=search_query_str,
                location=saved_search.location or None,
                work_mode=saved_search.work_mode
                if saved_search.work_mode != "any"
                else None,
                provider_id=provider_name,
                page=1,
                page_size=20,
            )
            search_result = await registry.search(query_obj)
            discovered_jobs = search_result.jobs
        except Exception as exc:
            logger.warning(
                "Provider %s query failed during scheduled scan: %s", provider_name, exc
            )
            # Re-raise to trigger worker bounded retry if transient
            raise

        scan_run.jobs_found = len(discovered_jobs)

        # 4. Check for cancellation after network fetch
        if await self.is_cancelled(scan_run.id, saved_search.id):
            scan_run.status = "cancelled"
            scan_run.error_message = (
                "Scan cancelled by user request after job discovery."
            )
            scan_run.completed_at = datetime.now(UTC)
            return scan_run

        # 5. Persist and deduplicate jobs idempotently
        persisted_jobs: list[JobPosting] = []
        new_jobs_count = 0
        for norm_job in discovered_jobs:
            # Filter employment type if configured
            if (
                saved_search.employment_type != "any"
                and norm_job.employment_type != saved_search.employment_type
            ):
                continue

            # Check if this exact job already existed before upserting
            existing_stmt = select(JobPosting.id).where(
                JobPosting.source == norm_job.source,
                JobPosting.source_id == norm_job.source_id,
            )
            already_existed = (
                await session.execute(existing_stmt)
            ).scalar_one_or_none() is not None

            job_record = await JobService.upsert_normalized_job(session, norm_job)
            persisted_jobs.append(job_record)
            if not already_existed:
                new_jobs_count += 1

        scan_run.new_jobs_ingested = new_jobs_count

        # 6. Evaluate candidate matching and generate high-match notifications
        high_matches_count = 0
        min_score = saved_search.min_match_score

        for job in persisted_jobs:
            if await self.is_cancelled(scan_run.id, saved_search.id):
                scan_run.status = "cancelled"
                scan_run.error_message = (
                    "Scan cancelled by user request during match evaluation."
                )
                scan_run.completed_at = datetime.now(UTC)
                return scan_run

            match = await MatchingService.evaluate_and_persist_match(
                session, user_id=user_id, job_id=job.id
            )
            if match and match.total_score >= min_score:
                high_matches_count += 1
                if saved_search.in_app_notifications:
                    await notification_service.create_notification(
                        session=session,
                        user_id=user_id,
                        type="high_match_job",
                        title=f"High Match Opportunity: {job.title}",
                        message=(
                            f"Discovered matching role at {job.company} with score of "
                            f"{match.total_score:.1f}% for your search '{saved_search.name}'."
                        ),
                        data={
                            "job_id": job.id,
                            "job_title": job.title,
                            "company": job.company,
                            "match_score": match.total_score,
                            "saved_search_id": saved_search.id,
                        },
                        email_requested=saved_search.email_notifications,
                    )

        scan_run.high_matches_found = high_matches_count

        # 7. Check for pending application review reminders
        pending_app_stmt = (
            select(JobApplication)
            .where(
                JobApplication.user_id == user_id,
                JobApplication.approval_status == "pending",
                JobApplication.status == "awaiting_approval",
            )
            .limit(1)
        )
        pending_app = (await session.execute(pending_app_stmt)).scalar_one_or_none()
        if pending_app:
            await notification_service.create_notification(
                session=session,
                user_id=user_id,
                type="pending_approval_reminder",
                title=f"Review Required: Application #{pending_app.id}",
                message=(
                    f"You have an application prepared for {pending_app.job.title if pending_app.job else 'target position'} "
                    "awaiting your explicit candidate approval."
                ),
                data={"application_id": pending_app.id},
                email_requested=saved_search.email_notifications,
            )

        scan_run.status = "completed"
        scan_run.completed_at = datetime.now(UTC)
        return scan_run
