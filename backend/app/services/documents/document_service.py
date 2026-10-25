"""Document Service orchestrating tailored resume and cover letter generation,
factual consistency validation, immutable version history, and document export.
"""

import logging
from typing import Any, List, Optional, Tuple
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import (
    DocumentVersion,
    GeneratedDocument,
    JobPosting,
    User,
)
from app.services.documents.cover_letter_agent import cover_letter_agent
from app.services.documents.docx_renderer import docx_renderer
from app.services.documents.factual_checker import factual_checker
from app.services.documents.pdf_renderer import pdf_renderer
from app.services.documents.resume_agent import resume_agent
from app.services.documents.schemas import (
    DocumentUpdateRequest,
    FactualValidationReport,
    StructuredCoverLetter,
    StructuredResume,
)

logger = logging.getLogger(__name__)


class DocumentService:
    """Service handling lifecycle of job-tailored documents and versioning."""

    @staticmethod
    async def load_candidate_facts(session: AsyncSession, user_id: int) -> Optional[User]:
        """Loads user with all verified profile facts."""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.profile),
                selectinload(User.skills),
                selectinload(User.educations),
                selectinload(User.experiences),
                selectinload(User.projects),
                selectinload(User.certifications),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def generate_document(
        session: AsyncSession,
        user_id: int,
        job_id: int,
        doc_type: str = "resume",
        template_id: str = "modern",
        custom_instructions: Optional[str] = None,
        require_live_llm: bool = False,
    ) -> Tuple[GeneratedDocument, DocumentVersion]:
        """
        Generates a tailored resume or cover letter for a job posting.
        Stores structured data, runs automated factual checker, and saves as new version.
        """
        candidate = await DocumentService.load_candidate_facts(session, user_id)
        if not candidate:
            raise ValueError(f"Candidate user {user_id} not found.")

        # Fetch job posting
        stmt_job = select(JobPosting).where(JobPosting.id == job_id)
        res_job = await session.execute(stmt_job)
        job = res_job.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job posting {job_id} not found.")

        candidate_version = candidate.profile.profile_version if candidate.profile else 1

        # Generate based on type
        if doc_type == "cover_letter":
            structured_data_obj, formatted_text, val_report, model_name, prompt_version = (
                await cover_letter_agent.generate_tailored_cover_letter(
                    candidate=candidate,
                    job=job,
                    custom_instructions=custom_instructions,
                    require_live_llm=require_live_llm,
                )
            )
            title = f"Cover Letter - {job.title} at {job.company}"
        else:
            doc_type = "resume"
            structured_data_obj, formatted_text, val_report, model_name, prompt_version = (
                await resume_agent.generate_tailored_resume(
                    candidate=candidate,
                    job=job,
                    custom_instructions=custom_instructions,
                    require_live_llm=require_live_llm,
                )
            )
            title = f"Tailored Resume - {job.title} at {job.company}"

        structured_dict = structured_data_obj.model_dump()

        # Find or create GeneratedDocument container
        stmt_doc = (
            select(GeneratedDocument)
            .where(
                GeneratedDocument.user_id == user_id,
                GeneratedDocument.job_id == job_id,
                GeneratedDocument.doc_type == doc_type,
            )
            .options(selectinload(GeneratedDocument.versions))
        )
        res_doc = await session.execute(stmt_doc)
        doc = res_doc.scalar_one_or_none()

        if not doc:
            doc = GeneratedDocument(
                user_id=user_id,
                job_id=job_id,
                doc_type=doc_type,
                title=title,
                template_id=template_id,
                candidate_profile_version=candidate_version,
            )
            session.add(doc)
            await session.flush()
            version_num = 1
        else:
            # Updating container metadata
            doc.title = title
            doc.template_id = template_id
            doc.candidate_profile_version = candidate_version
            version_num = len(doc.versions) + 1

        # Create immutable DocumentVersion
        new_version = DocumentVersion(
            document_id=doc.id,
            version_number=version_num,
            structured_data=structured_dict,
            formatted_text=formatted_text,
            model_name=model_name,
            prompt_version=prompt_version,
            validation_report=val_report.model_dump(),
            is_approved=False,
            change_summary=f"Generation for {job.title} (v{version_num})",
        )
        session.add(new_version)
        await session.commit()

        # Reload with eager relationships
        stmt_fresh = (
            select(GeneratedDocument)
            .where(GeneratedDocument.id == doc.id)
            .options(
                selectinload(GeneratedDocument.versions),
                selectinload(GeneratedDocument.job),
            )
        )
        res_fresh = await session.execute(stmt_fresh)
        loaded_doc = res_fresh.scalar_one()
        return loaded_doc, new_version

    @staticmethod
    async def edit_document_content(
        session: AsyncSession,
        user_id: int,
        document_id: int,
        update_data: DocumentUpdateRequest,
    ) -> DocumentVersion:
        """
        Edits document content by creating a NEW DocumentVersion without mutating earlier versions.
        Re-runs factual validation checker on modified structured data.
        """
        candidate = await DocumentService.load_candidate_facts(session, user_id)
        if not candidate:
            raise ValueError(f"Candidate user {user_id} not found.")

        # Fetch document with ownership check
        stmt_doc = (
            select(GeneratedDocument)
            .where(GeneratedDocument.id == document_id, GeneratedDocument.user_id == user_id)
            .options(selectinload(GeneratedDocument.versions), selectinload(GeneratedDocument.job))
        )
        res_doc = await session.execute(stmt_doc)
        doc = res_doc.scalar_one_or_none()
        if not doc:
            raise PermissionError("Document not found or access denied.")

        if update_data.template_id:
            doc.template_id = update_data.template_id

        # Re-run factual consistency validation on modified structured data
        if doc.doc_type == "cover_letter":
            try:
                letter_obj = StructuredCoverLetter.model_validate(update_data.structured_data)
                formatted_text = cover_letter_agent.render_to_plain_text(letter_obj)
                val_report = factual_checker.verify_cover_letter(letter_obj, candidate)
            except Exception as exc:
                raise ValueError(f"Malformed cover letter data: {exc}")
        else:
            try:
                resume_obj = StructuredResume.model_validate(update_data.structured_data)
                formatted_text = resume_agent.render_to_plain_text(resume_obj)
                val_report = factual_checker.verify_resume(resume_obj, candidate)
            except Exception as exc:
                raise ValueError(f"Malformed resume data: {exc}")

        # Determine next version number
        next_ver = len(doc.versions) + 1

        # Create new version preserving history
        new_version = DocumentVersion(
            document_id=doc.id,
            version_number=next_ver,
            structured_data=update_data.structured_data,
            formatted_text=formatted_text,
            model_name="user_editor",
            prompt_version="1.0.0",
            validation_report=val_report.model_dump(),
            is_approved=bool(update_data.is_approved),
            change_summary=update_data.change_summary or f"Manual edit v{next_ver}",
        )
        session.add(new_version)
        await session.commit()
        await session.refresh(new_version)

        return new_version

    @staticmethod
    async def get_document(
        session: AsyncSession,
        user_id: int,
        document_id: int,
    ) -> GeneratedDocument:
        """Fetches document with versions, enforcing user ownership."""
        stmt = (
            select(GeneratedDocument)
            .where(GeneratedDocument.id == document_id, GeneratedDocument.user_id == user_id)
            .options(
                selectinload(GeneratedDocument.versions),
                selectinload(GeneratedDocument.job),
            )
        )
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            raise PermissionError("Document not found or access denied.")
        return doc

    @staticmethod
    async def list_user_documents(
        session: AsyncSession,
        user_id: int,
        job_id: Optional[int] = None,
        doc_type: Optional[str] = None,
    ) -> List[GeneratedDocument]:
        """Lists generated documents for a user with optional job and type filters."""
        stmt = (
            select(GeneratedDocument)
            .where(GeneratedDocument.user_id == user_id)
            .options(
                selectinload(GeneratedDocument.versions),
                selectinload(GeneratedDocument.job),
            )
            .order_by(desc(GeneratedDocument.updated_at))
        )
        if job_id:
            stmt = stmt.where(GeneratedDocument.job_id == job_id)
        if doc_type:
            stmt = stmt.where(GeneratedDocument.doc_type == doc_type)

        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def render_export_file(
        session: AsyncSession,
        user_id: int,
        document_id: int,
        version_id: Optional[int] = None,
        export_format: str = "pdf",
    ) -> Tuple[bytes, str, str]:
        """
        Renders a document version to DOCX or PDF bytes.
        Returns (content_bytes, filename, media_type).
        """
        doc = await DocumentService.get_document(session, user_id, document_id)

        # Select target version (latest or specific version_id)
        target_version = None
        if version_id:
            target_version = next((v for v in doc.versions if v.id == version_id), None)
        if not target_version and doc.versions:
            target_version = doc.versions[0]  # ordered by version_number desc

        if not target_version:
            raise ValueError("No version exists for this document.")

        safe_title = "".join(c for c in doc.title if c.isalnum() or c in ("-", "_", " ")).strip().replace(" ", "_")
        if not safe_title:
            safe_title = f"{doc.doc_type}_{doc.id}"

        if export_format.lower() == "docx":
            if doc.doc_type == "cover_letter":
                content_bytes = docx_renderer.render_cover_letter(
                    target_version.structured_data, doc.template_id
                )
            else:
                content_bytes = docx_renderer.render_resume(
                    target_version.structured_data, doc.template_id
                )
            filename = f"{safe_title}_v{target_version.version_number}.docx"
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            # Default to PDF
            if doc.doc_type == "cover_letter":
                content_bytes = pdf_renderer.render_cover_letter(
                    target_version.structured_data, doc.template_id
                )
            else:
                content_bytes = pdf_renderer.render_resume(
                    target_version.structured_data, doc.template_id
                )
            filename = f"{safe_title}_v{target_version.version_number}.pdf"
            media_type = "application/pdf"

        return content_bytes, filename, media_type


document_service = DocumentService()
