from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import (
    Certification,
    Education,
    Experience,
    Profile,
    Project,
    Skill,
    User,
)
from app.schemas.auth import MessageResponse
from app.schemas.profile import (
    CertificationCreateRequest,
    CertificationResponse,
    EducationCreateRequest,
    EducationResponse,
    ExperienceCreateRequest,
    ExperienceResponse,
    FullCandidateProfileResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    ProjectCreateRequest,
    ProjectResponse,
    SkillCreateRequest,
    SkillResponse,
)
from app.services.matching_service import MatchingService

router = APIRouter(prefix="/profile", tags=["Candidate Profile"])


@router.get("/me", response_model=FullCandidateProfileResponse)
async def get_my_candidate_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FullCandidateProfileResponse:
    """Retrieve complete profile for the authenticated candidate with all related records."""
    stmt = (
        select(User)
        .where(User.id == current_user.id)
        .options(
            selectinload(User.profile),
            selectinload(User.skills),
            selectinload(User.educations),
            selectinload(User.experiences),
            selectinload(User.projects),
            selectinload(User.certifications),
        )
    )
    result = await db.execute(stmt)
    user_with_relations = result.scalar_one()

    # Ensure profile exists
    if not user_with_relations.profile:
        profile_obj = Profile(user_id=current_user.id)
        db.add(profile_obj)
        await db.commit()
        await db.refresh(user_with_relations)

    return FullCandidateProfileResponse(
        user_id=user_with_relations.id,
        email=user_with_relations.email,
        full_name=user_with_relations.full_name,
        profile=ProfileResponse.model_validate(user_with_relations.profile) if user_with_relations.profile else None,
        skills=[SkillResponse.model_validate(s) for s in user_with_relations.skills],
        educations=[EducationResponse.model_validate(e) for e in user_with_relations.educations],
        experiences=[ExperienceResponse.model_validate(x) for x in user_with_relations.experiences],
        projects=[ProjectResponse.model_validate(p) for p in user_with_relations.projects],
        certifications=[CertificationResponse.model_validate(c) for c in user_with_relations.certifications],
    )


@router.put("/me", response_model=ProfileResponse)
async def update_my_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update profile attributes for authenticated candidate."""
    stmt = select(Profile).where(Profile.user_id == current_user.id)
    profile = (await db.execute(stmt)).scalar_one_or_none()

    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)

    profile.profile_version = (profile.profile_version or 1) + 1
    await MatchingService.invalidate_stale_matches(db, current_user.id)
    await db.commit()
    await db.refresh(profile)
    return ProfileResponse.model_validate(profile)


# --- Skills Management with Ownership Enforcement ---
@router.post("/skills", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def add_skill(
    payload: SkillCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    """Add a new skill strictly attached to current authenticated user."""
    skill = Skill(
        user_id=current_user.id,
        name=payload.name.strip(),
        category=payload.category,
        proficiency_level=payload.proficiency_level,
        years_experience=payload.years_experience,
    )
    db.add(skill)
    await MatchingService.invalidate_stale_matches(db, current_user.id)
    await db.commit()
    await db.refresh(skill)
    return SkillResponse.model_validate(skill)


@router.delete("/skills/{skill_id}", response_model=MessageResponse)
async def delete_skill(
    skill_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a skill ensuring strict ownership check."""
    stmt = select(Skill).where(Skill.id == skill_id)
    skill = (await db.execute(stmt)).scalar_one_or_none()

    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")

    # Strict ownership check
    if skill.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this skill.")

    await db.delete(skill)
    await MatchingService.invalidate_stale_matches(db, current_user.id)
    await db.commit()
    return MessageResponse(message="Skill deleted successfully.")


# --- Education Management with Ownership Enforcement ---
@router.post("/education", response_model=EducationResponse, status_code=status.HTTP_201_CREATED)
async def add_education(
    payload: EducationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EducationResponse:
    """Add education record for current authenticated user."""
    education = Education(
        user_id=current_user.id,
        institution=payload.institution.strip(),
        degree=payload.degree.strip(),
        field_of_study=payload.field_of_study.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_current=payload.is_current,
        gpa=payload.gpa,
    )
    db.add(education)
    await db.commit()
    await db.refresh(education)
    return EducationResponse.model_validate(education)


@router.delete("/education/{education_id}", response_model=MessageResponse)
async def delete_education(
    education_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete education record ensuring strict ownership check."""
    stmt = select(Education).where(Education.id == education_id)
    edu = (await db.execute(stmt)).scalar_one_or_none()

    if not edu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Education record not found.")

    if edu.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this education record.")

    await db.delete(edu)
    await db.commit()
    return MessageResponse(message="Education record deleted successfully.")


# --- Experience Management with Ownership Enforcement ---
@router.post("/experience", response_model=ExperienceResponse, status_code=status.HTTP_201_CREATED)
async def add_experience(
    payload: ExperienceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperienceResponse:
    """Add professional experience record for current user."""
    exp = Experience(
        user_id=current_user.id,
        company=payload.company.strip(),
        title=payload.title.strip(),
        location=payload.location,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_current=payload.is_current,
        description=payload.description,
        achievements=payload.achievements,
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return ExperienceResponse.model_validate(exp)


@router.delete("/experience/{experience_id}", response_model=MessageResponse)
async def delete_experience(
    experience_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete experience record ensuring strict ownership check."""
    stmt = select(Experience).where(Experience.id == experience_id)
    exp = (await db.execute(stmt)).scalar_one_or_none()

    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience record not found.")

    if exp.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this experience record.")

    await db.delete(exp)
    await db.commit()
    return MessageResponse(message="Experience record deleted successfully.")


# --- Projects Management with Ownership Enforcement ---
@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def add_project(
    payload: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Add portfolio project for current user."""
    proj = Project(
        user_id=current_user.id,
        title=payload.title.strip(),
        description=payload.description,
        url=payload.url,
        repo_url=payload.repo_url,
        technologies=payload.technologies,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return ProjectResponse.model_validate(proj)


@router.delete("/projects/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete project ensuring strict ownership check."""
    stmt = select(Project).where(Project.id == project_id)
    proj = (await db.execute(stmt)).scalar_one_or_none()

    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    if proj.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this project.")

    await db.delete(proj)
    await db.commit()
    return MessageResponse(message="Project deleted successfully.")
