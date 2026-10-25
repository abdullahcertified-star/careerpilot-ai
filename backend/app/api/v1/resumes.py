from datetime import datetime
import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
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
    ProfileChangeLog,
    Project,
    ResumeExtraction,
    ResumeMetadata,
    Skill,
    User,
)
from app.schemas.auth import MessageResponse
from app.schemas.extraction import (
    ExtractedProfileData,
    ResumeConfirmRequest,
    ResumeExtractionResponse,
)
from app.services.document_parser import (
    extract_document_text,
    save_file_securely,
    validate_file_signature,
)
from app.services.extractor import fact_extractor

router = APIRouter(prefix="/resumes", tags=["Resume & CV Management"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Securely upload a candidate resume (PDF, DOCX, TXT).
    Validates file signature, detects MIME spoofing, and stores outside web root.
    """
    raw_content = await file.read()
    filename = file.filename or "resume.pdf"
    content_type = file.content_type or "application/octet-stream"

    # Validate file size, extension, and magic bytes
    doc_format = validate_file_signature(raw_content, filename, content_type)

    # Save to private per-user storage
    stored_path = save_file_securely(current_user.id, filename, raw_content)

    # Check if this should be the primary resume
    stmt = select(ResumeMetadata).where(ResumeMetadata.user_id == current_user.id)
    has_resumes = (await db.execute(stmt)).scalars().first() is not None

    metadata = ResumeMetadata(
        user_id=current_user.id,
        original_filename=Path(filename).name,
        stored_path=stored_path,
        file_size_bytes=len(raw_content),
        mime_type=file.content_type or f"application/{doc_format}",
        is_primary=not has_resumes,
    )
    db.add(metadata)
    await db.commit()
    await db.refresh(metadata)

    return {
        "id": metadata.id,
        "filename": metadata.original_filename,
        "size_bytes": metadata.file_size_bytes,
        "format": doc_format,
        "is_primary": metadata.is_primary,
        "created_at": metadata.created_at,
    }


@router.get("", response_model=List[dict])
async def list_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """List all uploaded resumes owned by the authenticated candidate."""
    stmt = (
        select(ResumeMetadata)
        .where(ResumeMetadata.user_id == current_user.id)
        .options(selectinload(ResumeMetadata.extraction))
        .order_by(ResumeMetadata.created_at.desc())
    )
    resumes = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": r.id,
            "filename": r.original_filename,
            "size_bytes": r.file_size_bytes,
            "mime_type": r.mime_type,
            "is_primary": r.is_primary,
            "has_parsed": r.extraction is not None,
            "parsing_status": r.extraction.status if r.extraction else "unparsed",
            "created_at": r.created_at,
        }
        for r in resumes
    ]


@router.get("/{resume_id}/download")
async def download_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Download original stored CV file with strict ownership check.
    Cross-user downloads are strictly denied.
    """
    stmt = select(ResumeMetadata).where(ResumeMetadata.id == resume_id)
    resume = (await db.execute(stmt)).scalar_one_or_none()

    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")

    if resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this resume.")

    file_path = Path(resume.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file could not be located on disk.")

    return FileResponse(
        path=str(file_path),
        filename=resume.original_filename,
        media_type=resume.mime_type,
    )


@router.delete("/{resume_id}", response_model=MessageResponse)
async def delete_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete resume record and remove file from disk with strict ownership check."""
    stmt = select(ResumeMetadata).where(ResumeMetadata.id == resume_id)
    resume = (await db.execute(stmt)).scalar_one_or_none()

    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")

    if resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this resume.")

    # Remove file from disk
    file_path = Path(resume.stored_path)
    if file_path.exists():
        try:
            os.remove(file_path)
        except OSError:
            pass

    await db.delete(resume)
    await db.commit()
    return MessageResponse(message="Resume and associated files deleted successfully.")


@router.post("/{resume_id}/parse", response_model=ResumeExtractionResponse)
async def parse_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeExtractionResponse:
    """
    Extract structured candidate facts from resume.
    Keeps extraction staged and separate from verified profile until confirmed.
    """
    stmt = (
        select(ResumeMetadata)
        .where(ResumeMetadata.id == resume_id)
        .options(selectinload(ResumeMetadata.extraction))
    )
    resume = (await db.execute(stmt)).scalar_one_or_none()

    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")

    if resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this resume.")

    file_path = Path(resume.stored_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical resume file missing from storage.")

    with open(file_path, "rb") as f:
        content = f.read()

    # Determine document format
    ext = file_path.suffix.lower().replace(".", "")
    doc_format = "pdf" if ext == "pdf" else "docx" if ext == "docx" else "txt"

    parsed_doc = extract_document_text(content, doc_format)
    extracted_data = fact_extractor.extract(parsed_doc)

    # Save or update extraction record
    if resume.extraction:
        extraction = resume.extraction
        extraction.raw_text = parsed_doc.full_text
        extraction.extracted_data = extracted_data.model_dump()
        extraction.page_count = parsed_doc.page_count
        extraction.status = "pending_review"
    else:
        extraction = ResumeExtraction(
            resume_id=resume.id,
            user_id=current_user.id,
            raw_text=parsed_doc.full_text,
            extracted_data=extracted_data.model_dump(),
            page_count=parsed_doc.page_count,
            status="pending_review",
        )
        db.add(extraction)

    await db.commit()
    await db.refresh(extraction)

    return ResumeExtractionResponse(
        id=extraction.id,
        resume_id=extraction.resume_id,
        user_id=extraction.user_id,
        status=extraction.status,
        page_count=extraction.page_count,
        extracted_data=ExtractedProfileData.model_validate(extraction.extracted_data),
    )


@router.get("/{resume_id}/extraction", response_model=ResumeExtractionResponse)
async def get_extraction(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeExtractionResponse:
    """Retrieve staged extracted facts with evidence snippets."""
    stmt = select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id)
    extraction = (await db.execute(stmt)).scalar_one_or_none()

    if not extraction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No extraction found for this resume.")

    if extraction.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this extraction.")

    return ResumeExtractionResponse(
        id=extraction.id,
        resume_id=extraction.resume_id,
        user_id=extraction.user_id,
        status=extraction.status,
        page_count=extraction.page_count,
        extracted_data=ExtractedProfileData.model_validate(extraction.extracted_data),
    )


@router.put("/{resume_id}/extraction", response_model=ResumeExtractionResponse)
async def update_extraction(
    resume_id: int,
    payload: ExtractedProfileData,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeExtractionResponse:
    """Allow candidate to edit/correct staged facts before confirming."""
    stmt = select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id)
    extraction = (await db.execute(stmt)).scalar_one_or_none()

    if not extraction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No extraction found for this resume.")

    if extraction.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this extraction.")

    extraction.extracted_data = payload.model_dump()
    await db.commit()
    await db.refresh(extraction)

    return ResumeExtractionResponse(
        id=extraction.id,
        resume_id=extraction.resume_id,
        user_id=extraction.user_id,
        status=extraction.status,
        page_count=extraction.page_count,
        extracted_data=ExtractedProfileData.model_validate(extraction.extracted_data),
    )


@router.post("/{resume_id}/extraction/confirm", response_model=MessageResponse)
async def confirm_extraction(
    resume_id: int,
    payload: ResumeConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Confirm staged extracted facts and merge confirmed items into verified candidate profile.
    Unsupported or unconfirmed claims are never added automatically.
    Preserves audit history via ProfileChangeLog.
    """
    stmt = select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id)
    extraction = (await db.execute(stmt)).scalar_one_or_none()

    if not extraction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No extraction found for this resume.")

    if extraction.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this extraction.")

    data = payload.data

    # 1. Update Profile fields if requested
    prof_stmt = select(Profile).where(Profile.user_id == current_user.id)
    profile = (await db.execute(prof_stmt)).scalar_one_or_none()
    if not profile:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    if payload.override_headline and data.headline:
        profile.headline = data.headline
    if payload.override_bio and data.bio:
        profile.bio = data.bio
    if payload.override_location and data.location:
        profile.location = data.location

    # 2. Add confirmed skills (avoid duplicates)
    existing_skills_stmt = select(Skill.name).where(Skill.user_id == current_user.id)
    existing_skills = set((await db.execute(existing_skills_stmt)).scalars().all())

    added_skills_count = 0
    for s in data.skills:
        if s.is_confirmed and s.name.lower() not in (name.lower() for name in existing_skills):
            db.add(
                Skill(
                    user_id=current_user.id,
                    name=s.name,
                    category=s.category,
                    proficiency_level=s.proficiency_level,
                    years_experience=s.years_experience,
                )
            )
            existing_skills.add(s.name)
            added_skills_count += 1

    # 3. Add confirmed experiences
    added_exp_count = 0
    for exp in data.experience:
        if exp.is_confirmed:
            db.add(
                Experience(
                    user_id=current_user.id,
                    company=exp.company,
                    title=exp.title,
                    location=exp.location,
                    is_current=exp.is_current,
                    description=exp.description,
                    achievements=exp.achievements,
                )
            )
            added_exp_count += 1

    # 4. Add confirmed education
    added_edu_count = 0
    for edu in data.education:
        if edu.is_confirmed:
            db.add(
                Education(
                    user_id=current_user.id,
                    institution=edu.institution,
                    degree=edu.degree,
                    field_of_study=edu.field_of_study,
                    gpa=edu.gpa,
                )
            )
            added_edu_count += 1

    # 5. Add confirmed projects
    for proj in data.projects:
        if proj.is_confirmed:
            db.add(
                Project(
                    user_id=current_user.id,
                    title=proj.title,
                    description=proj.description,
                    url=proj.url,
                    repo_url=proj.repo_url,
                    technologies=proj.technologies,
                )
            )

    # 6. Add confirmed certifications
    for cert in data.certifications:
        if cert.is_confirmed:
            db.add(
                Certification(
                    user_id=current_user.id,
                    name=cert.name,
                    issuer=cert.issuer,
                    credential_id=cert.credential_id,
                )
            )

    # Record profile change log for auditability
    change_log = ProfileChangeLog(
        user_id=current_user.id,
        source=f"resume_extraction:{resume_id}",
        changes={
            "added_skills": added_skills_count,
            "added_experiences": added_exp_count,
            "added_educations": added_edu_count,
            "headline_updated": payload.override_headline and bool(data.headline),
        },
    )
    db.add(change_log)

    extraction.status = "confirmed"
    await db.commit()

    return MessageResponse(
        message=f"Extraction verified! Added {added_skills_count} skills, {added_exp_count} experiences, and {added_edu_count} education records to verified profile."
    )
