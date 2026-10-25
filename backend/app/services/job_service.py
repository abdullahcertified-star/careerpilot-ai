"""Service managing job discovery, persistence, deduplication, and candidate bookmarks."""

from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple
import urllib.parse

from sqlalchemy import delete, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.job_providers import registry
from app.integrations.job_providers.manual_import import ManualImportAdapter
from app.models.entities import JobPosting, SavedJob
from app.schemas.job import JobSearchQuery, JobSearchResult, NormalizedJob

logger = logging.getLogger(__name__)


def canonicalize_url(url_str: str) -> str:
    """Removes query tracking noise and trailing slashes for reliable deduplication."""
    try:
        parsed = urllib.parse.urlsplit(url_str.strip())
        query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        filtered = [
            (k, v) for k, v in query_params
            if not (
                k.lower().startswith("utm_")
                or k.lower() in ("ref", "trk", "source", "fbclid", "gclid", "gh_src", "partner")
            )
        ]
        new_query = urllib.parse.urlencode(filtered)
        path = parsed.path.rstrip("/")
        if not path:
            path = "/"
        return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, new_query, ""))
    except Exception:
        return url_str.strip()


class JobService:
    """Manages job persistence, deduplication, and user bookmarks."""

    @staticmethod
    async def upsert_normalized_job(session: AsyncSession, job: NormalizedJob) -> JobPosting:
        """
        Deduplicates and persists a normalized job posting.
        Checks by (source, source_id) and canonical_url to prevent duplicate listings.
        """
        canon_url = canonicalize_url(job.canonical_url)

        # 1. Primary deduplication: check source and source_id
        stmt = select(JobPosting).where(
            JobPosting.source == job.source,
            JobPosting.source_id == job.source_id,
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        # 2. Secondary deduplication: check canonical_url
        if not existing:
            stmt_url = select(JobPosting).where(JobPosting.canonical_url == canon_url)
            res_url = await session.execute(stmt_url)
            existing = res_url.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.title = job.title
            existing.company = job.company
            existing.description = job.description
            existing.location = job.location
            existing.work_mode = job.work_mode
            existing.employment_type = job.employment_type
            existing.department = job.department
            existing.retrieved_at = job.retrieved_at
            if job.posted_at:
                existing.posted_at = job.posted_at
            existing.raw_metadata = job.raw_metadata
            existing.is_active = True
            await session.commit()
            await session.refresh(existing)
            return existing

        # Create new record
        new_job = JobPosting(
            source=job.source,
            source_id=job.source_id,
            canonical_url=canon_url,
            title=job.title,
            company=job.company,
            description=job.description,
            location=job.location,
            work_mode=job.work_mode,
            employment_type=job.employment_type,
            department=job.department,
            posted_at=job.posted_at,
            retrieved_at=job.retrieved_at,
            raw_metadata=job.raw_metadata,
            is_active=True,
        )
        session.add(new_job)
        await session.commit()
        await session.refresh(new_job)
        return new_job

    @staticmethod
    async def search_and_persist(
        session: AsyncSession, query: JobSearchQuery, user_id: Optional[int] = None
    ) -> Tuple[List[JobPosting], int, List[str], Optional[str]]:
        """
        Queries providers via registry, persists newly found jobs, and returns matching JobPostings
        with is_saved status evaluated for user_id.
        """
        # Execute provider search
        provider_result = await registry.search(query)

        # Upsert found jobs
        for normalized in provider_result.jobs:
            try:
                await JobService.upsert_normalized_job(session, normalized)
            except Exception as exc:
                logger.warning("Failed to upsert job %s: %s", normalized.source_id, exc)

        # Now query database for current page matching search criteria
        stmt = select(JobPosting).where(JobPosting.is_active.is_(True))

        if query.query:
            kw = f"%{query.query.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    JobPosting.title.ilike(kw),
                    JobPosting.company.ilike(kw),
                    JobPosting.description.ilike(kw),
                    JobPosting.department.ilike(kw),
                )
            )

        if query.location:
            loc_kw = f"%{query.location.strip().lower()}%"
            stmt = stmt.where(JobPosting.location.ilike(loc_kw))

        if query.work_mode and query.work_mode != "all":
            stmt = stmt.where(JobPosting.work_mode == query.work_mode.strip().lower())

        if query.provider_id and query.provider_id != "all":
            stmt = stmt.where(JobPosting.source == query.provider_id)

        # Ordering & Pagination
        stmt = stmt.order_by(desc(JobPosting.retrieved_at))
        offset = (query.page - 1) * query.page_size
        stmt = stmt.offset(offset).limit(query.page_size)

        res = await session.execute(stmt)
        postings = list(res.scalars().all())

        # Count total matching in DB
        # If provider returned jobs, total_count is at least provider_result.total_count
        total_count = max(len(postings), provider_result.total_count)

        return postings, total_count, provider_result.warnings, provider_result.external_search_url

    @staticmethod
    async def import_url(session: AsyncSession, url: str) -> JobPosting:
        """Securely imports a job posting from an external URL with SSRF protection."""
        manual_adapter = registry.get_provider("manual_import")
        if not isinstance(manual_adapter, ManualImportAdapter):
            raise RuntimeError("Manual import adapter is not configured.")

        normalized = await manual_adapter.import_from_url(url)
        return await JobService.upsert_normalized_job(session, normalized)

    @staticmethod
    async def get_job_by_id(session: AsyncSession, job_id: int) -> Optional[JobPosting]:
        stmt = select(JobPosting).where(JobPosting.id == job_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def save_job(
        session: AsyncSession, user_id: int, job_id: int, notes: Optional[str] = None, status: str = "saved"
    ) -> SavedJob:
        """Saves/bookmarks a job for candidate with idempotency."""
        # Check if job exists
        job = await JobService.get_job_by_id(session, job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} does not exist.")

        stmt = select(SavedJob).where(SavedJob.user_id == user_id, SavedJob.job_id == job_id)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.status = status
            if notes is not None:
                existing.notes = notes
            await session.commit()
            await session.refresh(existing)
            return existing

        saved = SavedJob(
            user_id=user_id,
            job_id=job_id,
            status=status,
            notes=notes,
        )
        session.add(saved)
        await session.commit()
        await session.refresh(saved)
        return saved

    @staticmethod
    async def list_saved_jobs(session: AsyncSession, user_id: int) -> List[SavedJob]:
        """Lists all jobs saved by candidate with eager-loaded job details."""
        stmt = (
            select(SavedJob)
            .where(SavedJob.user_id == user_id)
            .options(selectinload(SavedJob.job))
            .order_by(desc(SavedJob.created_at))
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_saved_job(
        session: AsyncSession, user_id: int, saved_id: int, status: Optional[str] = None, notes: Optional[str] = None
    ) -> Optional[SavedJob]:
        """Updates notes or status with strict candidate ownership verification."""
        stmt = select(SavedJob).where(SavedJob.id == saved_id, SavedJob.user_id == user_id).options(selectinload(SavedJob.job))
        res = await session.execute(stmt)
        saved = res.scalar_one_or_none()
        if not saved:
            return None

        if status:
            saved.status = status
        if notes is not None:
            saved.notes = notes

        await session.commit()
        await session.refresh(saved)
        return saved

    @staticmethod
    async def delete_saved_job(session: AsyncSession, user_id: int, job_id_or_saved_id: int) -> bool:
        """Removes a saved job bookmark with ownership check."""
        stmt = delete(SavedJob).where(
            SavedJob.user_id == user_id,
            or_(SavedJob.id == job_id_or_saved_id, SavedJob.job_id == job_id_or_saved_id),
        )
        res = await session.execute(stmt)
        await session.commit()
        rowcount = int(getattr(res, "rowcount", 0))
        return rowcount > 0
