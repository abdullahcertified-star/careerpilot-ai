"""Service coordinating deterministic matching evaluations, persistence, ranking, and cache invalidation."""

import logging
from typing import List, Optional, Tuple
from sqlalchemy import asc, desc, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import JobMatch, JobPosting, User
from app.services.matching.engine import DEFAULT_MATCHING_WEIGHTS, SCORING_VERSION, matching_engine

logger = logging.getLogger(__name__)


class MatchingService:
    """Coordinates match computation, ranking queries, and stale cache invalidation."""

    @staticmethod
    async def load_candidate_with_relations(session: AsyncSession, user_id: int) -> Optional[User]:
        """Eager-loads candidate user with all profile components required for matching."""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.profile),
                selectinload(User.skills),
                selectinload(User.educations),
                selectinload(User.experiences),
                selectinload(User.certifications),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def evaluate_and_persist_match(
        session: AsyncSession, user_id: int, job_id: int, force: bool = False
    ) -> Optional[JobMatch]:
        """
        Computes deterministic match between candidate and a job.
        Checks profile version and updates existing record or inserts new one.
        """
        candidate = await MatchingService.load_candidate_with_relations(session, user_id)
        if not candidate:
            return None

        # Load job posting
        stmt_job = select(JobPosting).where(JobPosting.id == job_id)
        res_job = await session.execute(stmt_job)
        job = res_job.scalar_one_or_none()
        if not job:
            return None

        profile_version = candidate.profile.profile_version if candidate.profile else 1

        # Check existing match
        stmt_match = select(JobMatch).where(
            JobMatch.user_id == user_id, JobMatch.job_id == job_id
        ).options(selectinload(JobMatch.job))
        res_match = await session.execute(stmt_match)
        existing = res_match.scalar_one_or_none()

        if existing and not force and not existing.is_stale and existing.candidate_profile_version == profile_version:
            return existing

        # Evaluate deterministically
        breakdown = matching_engine.evaluate_match(candidate, job)

        if existing:
            existing.total_score = breakdown.total_score
            existing.component_scores = breakdown.component_scores
            existing.matched_skills = breakdown.matched_skills
            existing.missing_skills = breakdown.missing_skills
            existing.missing_preferred_skills = breakdown.missing_preferred_skills
            existing.explanation = breakdown.explanation
            existing.candidate_profile_version = profile_version
            existing.scoring_version = SCORING_VERSION
            existing.is_stale = False
            await session.commit()
            await session.refresh(existing)
            return existing

        new_match = JobMatch(
            user_id=user_id,
            job_id=job_id,
            total_score=breakdown.total_score,
            component_scores=breakdown.component_scores,
            matched_skills=breakdown.matched_skills,
            missing_skills=breakdown.missing_skills,
            missing_preferred_skills=breakdown.missing_preferred_skills,
            explanation=breakdown.explanation,
            candidate_profile_version=profile_version,
            scoring_version=SCORING_VERSION,
            is_stale=False,
        )
        session.add(new_match)
        await session.commit()
        await session.refresh(new_match)
        new_match.job = job
        return new_match

    @staticmethod
    async def recalculate_all_matches(
        session: AsyncSession, user_id: int, limit: int = 100
    ) -> int:
        """Recalculates match scores for all active jobs against candidate profile."""
        candidate = await MatchingService.load_candidate_with_relations(session, user_id)
        if not candidate:
            return 0

        # Fetch existing match job IDs for candidate to guarantee all stale matches are refreshed
        existing_matches_stmt = select(JobMatch.job_id).where(JobMatch.user_id == user_id)
        existing_job_ids = list((await session.execute(existing_matches_stmt)).scalars().all())

        # Fetch active job postings
        stmt = (
            select(JobPosting.id)
            .where(JobPosting.is_active.is_(True))
            .order_by(desc(JobPosting.retrieved_at))
            .limit(limit)
        )
        res = await session.execute(stmt)
        active_job_ids = list(res.scalars().all())

        target_job_ids = list(dict.fromkeys(existing_job_ids + active_job_ids))

        count = 0
        for job_id in target_job_ids:
            try:
                await MatchingService.evaluate_and_persist_match(session, user_id, job_id, force=True)
                count += 1
            except Exception as exc:
                logger.warning("Error evaluating match for user %s on job %s: %s", user_id, job_id, exc)

        return count

    @staticmethod
    async def invalidate_stale_matches(session: AsyncSession, user_id: int) -> int:
        """
        Marks all existing match records for candidate as stale when profile changes,
        and increments profile version.
        """
        # Increment profile version
        candidate = await MatchingService.load_candidate_with_relations(session, user_id)
        if candidate and candidate.profile:
            candidate.profile.profile_version += 1

        stmt = update(JobMatch).where(JobMatch.user_id == user_id).values(is_stale=True)
        res = await session.execute(stmt)
        await session.commit()
        return int(getattr(res, "rowcount", 0))

    @staticmethod
    async def get_ranked_matches(
        session: AsyncSession,
        user_id: int,
        min_score: Optional[float] = None,
        work_mode: Optional[str] = None,
        location: Optional[str] = None,
        role: Optional[str] = None,
        company: Optional[str] = None,
        sort_by: str = "score_desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[JobMatch], int, int]:
        """
        Queries and filters candidate job matches with sorting, pagination, and auto-evaluation of un-scored jobs.
        """
        candidate = await MatchingService.load_candidate_with_relations(session, user_id)
        profile_version = candidate.profile.profile_version if candidate and candidate.profile else 1

        # Check if matches exist; if none exist or few, auto-evaluate active jobs
        stmt_count = select(JobMatch).where(JobMatch.user_id == user_id)
        existing_matches_res = await session.execute(stmt_count)
        if len(existing_matches_res.scalars().all()) == 0:
            await MatchingService.recalculate_all_matches(session, user_id, limit=50)

        # Build query joining JobMatch and JobPosting
        stmt = (
            select(JobMatch)
            .join(JobPosting, JobMatch.job_id == JobPosting.id)
            .where(JobMatch.user_id == user_id, JobPosting.is_active.is_(True))
            .options(selectinload(JobMatch.job))
        )

        if min_score is not None:
            stmt = stmt.where(JobMatch.total_score >= min_score)

        if work_mode and work_mode != "all":
            stmt = stmt.where(JobPosting.work_mode == work_mode.lower())

        if location:
            loc_kw = f"%{location.strip().lower()}%"
            stmt = stmt.where(JobPosting.location.ilike(loc_kw))

        if role:
            role_kw = f"%{role.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    JobPosting.title.ilike(role_kw),
                    JobPosting.department.ilike(role_kw),
                )
            )

        if company:
            comp_kw = f"%{company.strip().lower()}%"
            stmt = stmt.where(JobPosting.company.ilike(comp_kw))

        # Sorting
        if sort_by == "score_asc":
            stmt = stmt.order_by(asc(JobMatch.total_score))
        elif sort_by == "date_desc":
            stmt = stmt.order_by(desc(JobPosting.posted_at), desc(JobPosting.retrieved_at))
        elif sort_by == "title_asc":
            stmt = stmt.order_by(asc(JobPosting.title))
        elif sort_by == "company_asc":
            stmt = stmt.order_by(asc(JobPosting.company))
        else:  # score_desc (default)
            stmt = stmt.order_by(desc(JobMatch.total_score), desc(JobPosting.retrieved_at))

        # Count total
        res_all = await session.execute(stmt)
        all_matches = list(res_all.scalars().all())
        total_count = len(all_matches)

        # Pagination
        offset = (page - 1) * page_size
        paginated_matches = all_matches[offset : offset + page_size]

        return paginated_matches, total_count, profile_version
