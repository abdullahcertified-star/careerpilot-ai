"""Orchestration service for Phase 8 user-configured saved searches and scheduled discovery."""

import logging
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import SavedSearch, ScheduledScanRun
from app.services.scheduler.redis_client import check_redis_availability
from app.services.scheduler.schemas import (
    SavedSearchCreate,
    SavedSearchResponse,
    SavedSearchUpdate,
    ScheduledScanRunResponse,
)
from app.services.scheduler.worker import scheduled_scan_worker

logger = logging.getLogger(__name__)


class SavedSearchService:
    """Manages lifecycle, scheduling, pausing, and execution triggers for saved searches."""

    @staticmethod
    async def create_saved_search(
        session: AsyncSession,
        user_id: int,
        payload: SavedSearchCreate,
    ) -> SavedSearch:
        """Create a user-configured saved search and schedule its initial run."""
        # Verify Redis availability to alert immediately on missing service
        await check_redis_availability()

        now = datetime.now(UTC)
        search = SavedSearch(
            user_id=user_id,
            name=payload.name.strip(),
            role=payload.role.strip() if payload.role else None,
            keywords=[k.strip() for k in payload.keywords if k.strip()],
            location=payload.location.strip() if payload.location else None,
            work_mode=payload.work_mode.lower(),
            employment_type=payload.employment_type.lower(),
            min_match_score=payload.min_match_score,
            interval_minutes=payload.interval_minutes,
            provider_id=payload.provider_id.lower(),
            is_active=True,
            in_app_notifications=payload.in_app_notifications,
            email_notifications=payload.email_notifications,
            next_run_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(search)
        await session.commit()
        await session.refresh(search)
        return search

    @staticmethod
    async def list_saved_searches(
        session: AsyncSession,
        user_id: int,
    ) -> list[SavedSearch]:
        """List all saved searches for candidate with scan runs."""
        stmt = (
            select(SavedSearch)
            .where(SavedSearch.user_id == user_id)
            .options(selectinload(SavedSearch.scan_runs))
            .order_by(desc(SavedSearch.created_at))
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_saved_search(
        session: AsyncSession,
        user_id: int,
        search_id: int,
    ) -> SavedSearch | None:
        """Fetch saved search by ID with ownership verification."""
        stmt = (
            select(SavedSearch)
            .where(SavedSearch.id == search_id, SavedSearch.user_id == user_id)
            .options(selectinload(SavedSearch.scan_runs))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def update_saved_search(
        session: AsyncSession,
        user_id: int,
        search_id: int,
        payload: SavedSearchUpdate,
    ) -> SavedSearch | None:
        """Update criteria or configuration for an existing saved search."""
        search = await SavedSearchService.get_saved_search(session, user_id, search_id)
        if not search:
            return None

        if payload.name is not None:
            search.name = payload.name.strip()
        if payload.role is not None:
            search.role = payload.role.strip() if payload.role else None
        if payload.keywords is not None:
            search.keywords = [k.strip() for k in payload.keywords if k.strip()]
        if payload.location is not None:
            search.location = payload.location.strip() if payload.location else None
        if payload.work_mode is not None:
            search.work_mode = payload.work_mode.lower()
        if payload.employment_type is not None:
            search.employment_type = payload.employment_type.lower()
        if payload.min_match_score is not None:
            search.min_match_score = payload.min_match_score
        if payload.interval_minutes is not None:
            search.interval_minutes = payload.interval_minutes
        if payload.provider_id is not None:
            search.provider_id = payload.provider_id.lower()
        if payload.in_app_notifications is not None:
            search.in_app_notifications = payload.in_app_notifications
        if payload.email_notifications is not None:
            search.email_notifications = payload.email_notifications

        search.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(search)
        return search

    @staticmethod
    async def pause_saved_search(
        session: AsyncSession,
        user_id: int,
        search_id: int,
    ) -> SavedSearch | None:
        """Pause scheduling for a saved search."""
        search = await SavedSearchService.get_saved_search(session, user_id, search_id)
        if not search:
            return None

        search.is_active = False
        search.next_run_at = None
        search.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(search)
        return search

    @staticmethod
    async def resume_saved_search(
        session: AsyncSession,
        user_id: int,
        search_id: int,
    ) -> SavedSearch | None:
        """Resume scheduling for a paused search."""
        search = await SavedSearchService.get_saved_search(session, user_id, search_id)
        if not search:
            return None

        now = datetime.now(UTC)
        search.is_active = True
        search.next_run_at = now
        search.updated_at = now
        await session.commit()
        await session.refresh(search)
        return search

    @staticmethod
    async def delete_saved_search(
        session: AsyncSession,
        user_id: int,
        search_id: int,
    ) -> bool:
        """Delete saved search and remove any queued runs."""
        search = await SavedSearchService.get_saved_search(session, user_id, search_id)
        if not search:
            return False

        await session.delete(search)
        await session.commit()
        return True

    @staticmethod
    async def trigger_immediate_scan(
        session: AsyncSession,
        user_id: int,
        search_id: int,
    ) -> ScheduledScanRun:
        """Trigger an on-demand immediate execution of a saved search scan."""
        search = await SavedSearchService.get_saved_search(session, user_id, search_id)
        if not search:
            raise ValueError(f"Saved search {search_id} not found or access denied")

        return await scheduled_scan_worker.execute_search_scan(search_id)

    @staticmethod
    async def cancel_running_scan(
        session: AsyncSession,
        user_id: int,
        search_id: int,
    ) -> bool:
        """Request cancellation of an in-progress scan for saved search."""
        search = await SavedSearchService.get_saved_search(session, user_id, search_id)
        if not search:
            raise ValueError(f"Saved search {search_id} not found or access denied")

        # Find latest running run
        running_stmt = (
            select(ScheduledScanRun)
            .where(
                ScheduledScanRun.saved_search_id == search_id,
                ScheduledScanRun.status == "running",
            )
            .order_by(desc(ScheduledScanRun.started_at))
        )
        running_run = (await session.execute(running_stmt)).scalars().first()
        run_id = running_run.id if running_run else None

        await scheduled_scan_worker.request_scan_cancellation(search_id, run_id)
        if running_run:
            running_run.status = "cancelled"
            running_run.completed_at = datetime.now(UTC)
            running_run.error_message = "Scan cancelled by user request"
            await session.commit()

        return True

    @staticmethod
    async def get_scan_runs(
        session: AsyncSession,
        user_id: int,
        search_id: int,
    ) -> list[ScheduledScanRun]:
        """Retrieve execution history runs for a saved search."""
        search = await SavedSearchService.get_saved_search(session, user_id, search_id)
        if not search:
            raise ValueError(f"Saved search {search_id} not found or access denied")

        stmt = (
            select(ScheduledScanRun)
            .where(ScheduledScanRun.saved_search_id == search_id)
            .order_by(desc(ScheduledScanRun.started_at))
        )
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    def to_response(search: SavedSearch) -> SavedSearchResponse:
        """Convert SavedSearch model to SavedSearchResponse schema with latest run."""
        latest_run_resp: ScheduledScanRunResponse | None = None
        if search.scan_runs:
            latest_run_resp = ScheduledScanRunResponse.model_validate(
                search.scan_runs[0]
            )

        return SavedSearchResponse(
            id=search.id,
            user_id=search.user_id,
            name=search.name,
            role=search.role,
            keywords=search.keywords or [],
            location=search.location,
            work_mode=search.work_mode,
            employment_type=search.employment_type,
            min_match_score=search.min_match_score,
            interval_minutes=search.interval_minutes,
            provider_id=search.provider_id,
            is_active=search.is_active,
            in_app_notifications=search.in_app_notifications,
            email_notifications=search.email_notifications,
            last_run_at=search.last_run_at,
            last_success_at=search.last_success_at,
            last_failure_at=search.last_failure_at,
            next_run_at=search.next_run_at,
            last_error=search.last_error,
            consecutive_failures=search.consecutive_failures,
            total_runs_count=search.total_runs_count,
            created_at=search.created_at,
            updated_at=search.updated_at,
            latest_run=latest_run_resp,
        )


saved_search_service = SavedSearchService()
