"""Job discovery, provider integration, URL import, and saved jobs endpoints."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_current_user
from app.core.database import get_db
from app.core.rate_limit import rate_limit_general
from app.integrations.job_providers import registry
from app.models.entities import SavedJob, User
from app.schemas.auth import MessageResponse
from app.schemas.job import (
    JobImportRequest,
    JobPostingResponse,
    JobSearchQuery,
    ProviderCapabilities,
    SavedJobCreate,
    SavedJobResponse,
    SavedJobUpdate,
)
from app.services.job_service import JobService
from app.services.ssrf_protector import SSRFSecurityError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Job Discovery"])


@router.get("/providers", response_model=List[ProviderCapabilities])
async def list_job_providers() -> List[ProviderCapabilities]:
    """Lists registered job discovery provider adapters and their integration capabilities."""
    return registry.list_capabilities()


@router.get("/search")
async def search_jobs(
    query: Optional[str] = Query(None, description="Keywords matching title, description, or department"),
    location: Optional[str] = Query(None, description="Location filter"),
    work_mode: Optional[str] = Query(None, description="Filter by remote, hybrid, or onsite"),
    provider_id: Optional[str] = Query("greenhouse", description="Provider ID or 'all'"),
    board_token: Optional[str] = Query(None, description="Greenhouse board token e.g. gitlab, cloudflare"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """
    Searches jobs across providers, deduplicates and caches in PostgreSQL/SQLite,
    and returns paginated listings with provider attribution and candidate bookmark state.
    """
    search_query = JobSearchQuery(
        query=query,
        location=location,
        work_mode=work_mode,
        provider_id=provider_id,
        board_token=board_token,
        page=page,
        page_size=page_size,
    )

    user_id = current_user.id if current_user else None
    postings, total_count, warnings, ext_url = await JobService.search_and_persist(db, search_query, user_id=user_id)

    # Resolve saved job mapping for the current user if logged in
    saved_map: Dict[int, SavedJob] = {}
    if user_id:
        stmt = select(SavedJob).where(SavedJob.user_id == user_id)
        res = await db.execute(stmt)
        for s in res.scalars().all():
            saved_map[s.job_id] = s

    # Transform into JobPostingResponse
    items = []
    for p in postings:
        saved_entry = saved_map.get(p.id)
        resp = JobPostingResponse(
            id=p.id,
            source=p.source,
            source_id=p.source_id,
            canonical_url=p.canonical_url,
            title=p.title,
            company=p.company,
            description=p.description,
            location=p.location,
            work_mode=p.work_mode,
            employment_type=p.employment_type,
            department=p.department,
            posted_at=p.posted_at,
            retrieved_at=p.retrieved_at,
            raw_metadata=p.raw_metadata,
            is_active=p.is_active,
            is_saved=saved_entry is not None,
            saved_id=saved_entry.id if saved_entry else None,
            saved_status=saved_entry.status if saved_entry else None,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        items.append(resp)

    return {
        "items": [item.model_dump() for item in items],
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "has_more": (page * page_size) < total_count,
        "warnings": warnings,
        "external_search_url": ext_url,
    }


@router.post(
    "/import-url",
    response_model=JobPostingResponse,
    dependencies=[Depends(rate_limit_general)],
)
async def import_job_from_url(
    payload: JobImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobPostingResponse:
    """
    Imports and normalizes a job posting from an external URL.
    Enforces SSRF prevention, redirect limits, and HTML sanitization.
    """
    if not payload.url or not payload.url.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A non-empty URL string is required.",
        )

    try:
        job = await JobService.import_url(db, payload.url.strip())
        return JobPostingResponse(
            id=job.id,
            source=job.source,
            source_id=job.source_id,
            canonical_url=job.canonical_url,
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
            is_active=job.is_active,
            is_saved=False,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
    except SSRFSecurityError as exc:
        logger.warning("SSRF attempt blocked for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security rejection: {str(exc)}",
        )
    except (TimeoutError, ConnectionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Failed to fetch job posting from URL: {str(exc)}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse job posting from URL: {str(exc)}",
        )
    except Exception as exc:
        logger.error("Unexpected error importing job URL: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing job import request.",
        )


@router.get("/saved", response_model=List[SavedJobResponse])
async def list_saved_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SavedJobResponse]:
    """Retrieves all bookmarked jobs for the current candidate with ownership enforcement."""
    saved_records = await JobService.list_saved_jobs(db, current_user.id)
    results = []
    for s in saved_records:
        job_resp = JobPostingResponse(
            id=s.job.id,
            source=s.job.source,
            source_id=s.job.source_id,
            canonical_url=s.job.canonical_url,
            title=s.job.title,
            company=s.job.company,
            description=s.job.description,
            location=s.job.location,
            work_mode=s.job.work_mode,
            employment_type=s.job.employment_type,
            department=s.job.department,
            posted_at=s.job.posted_at,
            retrieved_at=s.job.retrieved_at,
            raw_metadata=s.job.raw_metadata,
            is_active=s.job.is_active,
            is_saved=True,
            saved_id=s.id,
            saved_status=s.status,
            created_at=s.job.created_at,
            updated_at=s.job.updated_at,
        )
        results.append(
            SavedJobResponse(
                id=s.id,
                user_id=s.user_id,
                job_id=s.job_id,
                status=s.status,
                notes=s.notes,
                created_at=s.created_at,
                updated_at=s.updated_at,
                job=job_resp,
            )
        )
    return results


@router.post("/{id}/save", response_model=SavedJobResponse)
async def save_job(
    id: int,
    payload: Optional[SavedJobCreate] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedJobResponse:
    """Bookmarks a job posting for the current candidate."""
    notes = payload.notes if payload else None
    save_status = payload.status if payload else "saved"

    try:
        saved = await JobService.save_job(db, current_user.id, id, notes=notes, status=save_status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    job = await JobService.get_job_by_id(db, id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job_resp = JobPostingResponse(
        id=job.id,
        source=job.source,
        source_id=job.source_id,
        canonical_url=job.canonical_url,
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
        is_active=job.is_active,
        is_saved=True,
        saved_id=saved.id,
        saved_status=saved.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )

    return SavedJobResponse(
        id=saved.id,
        user_id=saved.user_id,
        job_id=saved.job_id,
        status=saved.status,
        notes=saved.notes,
        created_at=saved.created_at,
        updated_at=saved.updated_at,
        job=job_resp,
    )


@router.delete("/{id}/save", response_model=MessageResponse)
async def unsave_job(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Removes a saved job bookmark."""
    deleted = await JobService.delete_saved_job(db, current_user.id, id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved job bookmark not found or already deleted.",
        )
    return MessageResponse(message="Job bookmark successfully removed.")


@router.patch("/saved/{saved_id}", response_model=SavedJobResponse)
async def update_saved_job(
    saved_id: int,
    payload: SavedJobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SavedJobResponse:
    """Updates notes or status on a saved job bookmark with strict ownership check."""
    updated = await JobService.update_saved_job(
        db,
        user_id=current_user.id,
        saved_id=saved_id,
        status=payload.status,
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved job not found or you do not have permission to modify it.",
        )

    job_resp = JobPostingResponse(
        id=updated.job.id,
        source=updated.job.source,
        source_id=updated.job.source_id,
        canonical_url=updated.job.canonical_url,
        title=updated.job.title,
        company=updated.job.company,
        description=updated.job.description,
        location=updated.job.location,
        work_mode=updated.job.work_mode,
        employment_type=updated.job.employment_type,
        department=updated.job.department,
        posted_at=updated.job.posted_at,
        retrieved_at=updated.job.retrieved_at,
        raw_metadata=updated.job.raw_metadata,
        is_active=updated.job.is_active,
        is_saved=True,
        saved_id=updated.id,
        saved_status=updated.status,
        created_at=updated.job.created_at,
        updated_at=updated.job.updated_at,
    )

    return SavedJobResponse(
        id=updated.id,
        user_id=updated.user_id,
        job_id=updated.job_id,
        status=updated.status,
        notes=updated.notes,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        job=job_resp,
    )


@router.get("/{id}", response_model=JobPostingResponse)
async def get_job_details(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> JobPostingResponse:
    """Retrieves detailed information for a single job posting."""
    job = await JobService.get_job_by_id(db, id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job posting not found.")

    is_saved = False
    saved_id = None
    saved_status = None
    if current_user:
        stmt = select(SavedJob).where(SavedJob.user_id == current_user.id, SavedJob.job_id == job.id)
        res = await db.execute(stmt)
        saved = res.scalar_one_or_none()
        if saved:
            is_saved = True
            saved_id = saved.id
            saved_status = saved.status

    return JobPostingResponse(
        id=job.id,
        source=job.source,
        source_id=job.source_id,
        canonical_url=job.canonical_url,
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
        is_active=job.is_active,
        is_saved=is_saved,
        saved_id=saved_id,
        saved_status=saved_status,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
