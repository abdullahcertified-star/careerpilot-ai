"""API router for deterministic job matching, ranking, and scoring."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import User
from app.schemas.auth import MessageResponse
from app.schemas.job import JobPostingResponse
from app.schemas.matching import (
    ComponentScores,
    JobMatchResponse,
    MatchPreferencesUpdate,
    RankedMatchListResponse,
    ScoringWeightsResponse,
)
from app.services.matching.engine import DEFAULT_MATCHING_WEIGHTS, SCORING_VERSION
from app.services.matching_service import MatchingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["Job Matching & Ranking"])


@router.get("/weights", response_model=ScoringWeightsResponse)
async def get_scoring_weights() -> ScoringWeightsResponse:
    """Returns the active deterministic scoring weights configuration and version."""
    return ScoringWeightsResponse(
        scoring_version=SCORING_VERSION,
        weights=DEFAULT_MATCHING_WEIGHTS,
        description=(
            "Deterministic scoring breakdown: Required skills (35%), Responsibilities & Role relevance (25%), "
            "Experience & Seniority (15%), Education & Certifications (10%), Location & Work auth (10%), Preferred skills (5%)."
        ),
    )


@router.get("", response_model=RankedMatchListResponse)
async def get_ranked_matches(
    min_score: Optional[float] = Query(None, ge=0.0, le=100.0, description="Minimum match score threshold (0-100)"),
    work_mode: Optional[str] = Query(None, description="Filter by work mode: remote, hybrid, onsite"),
    location: Optional[str] = Query(None, description="Filter by location"),
    role: Optional[str] = Query(None, description="Filter by role or job title"),
    company: Optional[str] = Query(None, description="Filter by company name"),
    sort_by: str = Query("score_desc", description="Sorting: score_desc, score_asc, date_desc, title_asc, company_asc"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RankedMatchListResponse:
    """
    Retrieves ranked job postings tailored to candidate profile using deterministic scoring.
    Supports multi-attribute filtering and explainable breakdown.
    """
    matches, total_count, profile_version = await MatchingService.get_ranked_matches(
        db,
        user_id=current_user.id,
        min_score=min_score,
        work_mode=work_mode,
        location=location,
        role=role,
        company=company,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

    items = []
    for m in matches:
        comp_dict = m.component_scores or {}
        comp_scores = ComponentScores(
            required_skills=float(comp_dict.get("required_skills", 0.0)),
            role_relevance=float(comp_dict.get("role_relevance", 0.0)),
            experience_seniority=float(comp_dict.get("experience_seniority", 0.0)),
            education_certifications=float(comp_dict.get("education_certifications", 0.0)),
            location_work_authorization=float(comp_dict.get("location_work_authorization", 0.0)),
            preferred_skills=float(comp_dict.get("preferred_skills", 0.0)),
        )

        job_resp = None
        if m.job:
            job_resp = JobPostingResponse.model_validate(m.job)

        items.append(
            JobMatchResponse(
                id=m.id,
                user_id=m.user_id,
                job_id=m.job_id,
                total_score=m.total_score,
                component_scores=comp_scores,
                weights_used=DEFAULT_MATCHING_WEIGHTS,
                matched_skills=m.matched_skills or [],
                missing_skills=m.missing_skills or [],
                missing_preferred_skills=m.missing_preferred_skills or [],
                explanation=m.explanation,
                candidate_profile_version=m.candidate_profile_version,
                scoring_version=m.scoring_version,
                is_stale=m.is_stale,
                created_at=m.created_at,
                updated_at=m.updated_at,
                job=job_resp,
            )
        )

    return RankedMatchListResponse(
        items=items,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total_count,
        scoring_version=SCORING_VERSION,
        profile_version=profile_version,
    )


@router.get("/{job_id}", response_model=JobMatchResponse)
async def get_match_detail(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobMatchResponse:
    """Retrieves or calculates detailed match analysis for a specific job posting."""
    match = await MatchingService.evaluate_and_persist_match(db, current_user.id, job_id)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job posting or candidate profile not found.")

    comp_dict = match.component_scores or {}
    comp_scores = ComponentScores(
        required_skills=float(comp_dict.get("required_skills", 0.0)),
        role_relevance=float(comp_dict.get("role_relevance", 0.0)),
        experience_seniority=float(comp_dict.get("experience_seniority", 0.0)),
        education_certifications=float(comp_dict.get("education_certifications", 0.0)),
        location_work_authorization=float(comp_dict.get("location_work_authorization", 0.0)),
        preferred_skills=float(comp_dict.get("preferred_skills", 0.0)),
    )

    job_resp = JobPostingResponse.model_validate(match.job) if match.job else None

    return JobMatchResponse(
        id=match.id,
        user_id=match.user_id,
        job_id=match.job_id,
        total_score=match.total_score,
        component_scores=comp_scores,
        weights_used=DEFAULT_MATCHING_WEIGHTS,
        matched_skills=match.matched_skills or [],
        missing_skills=match.missing_skills or [],
        missing_preferred_skills=match.missing_preferred_skills or [],
        explanation=match.explanation,
        candidate_profile_version=match.candidate_profile_version,
        scoring_version=match.scoring_version,
        is_stale=match.is_stale,
        created_at=match.created_at,
        updated_at=match.updated_at,
        job=job_resp,
    )


@router.post("/recalculate", response_model=MessageResponse)
async def recalculate_candidate_matches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Triggers an on-demand re-evaluation of candidate compatibility against all active job listings."""
    count = await MatchingService.recalculate_all_matches(db, current_user.id)
    return MessageResponse(message=f"Successfully re-evaluated {count} job matches against candidate profile.")


@router.put("/preferences", response_model=MessageResponse)
async def update_matching_preferences(
    payload: MatchPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Updates matching criteria (target titles, remote preference, location, work auth) and marks matches stale."""
    candidate = await MatchingService.load_candidate_with_relations(db, current_user.id)
    if not candidate or not candidate.profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate profile not found.")

    prof = candidate.profile
    if payload.target_job_titles is not None:
        prof.target_job_titles = payload.target_job_titles
    if payload.location is not None:
        prof.location = payload.location
    if payload.remote_preference is not None:
        prof.remote_preference = payload.remote_preference
    if payload.work_authorization_status is not None:
        prof.work_authorization_status = payload.work_authorization_status

    # Invalidate stale matches and bump profile version
    await MatchingService.invalidate_stale_matches(db, current_user.id)
    await db.commit()

    return MessageResponse(message="Matching preferences updated. Existing matches marked for recalculation.")
