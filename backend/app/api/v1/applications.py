"""API endpoints for Phase 6 durable LangGraph workflow and human approval."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import User
from app.services.submission.schemas import (
    ApplicationApprovalReviewRequest,
    ApplicationPackage,
    ApplicationSubmitRequest,
    DocumentSelectionUpdateRequest,
    FormAnswersUpdateRequest,
    SubmissionAttemptResponse,
    SubmissionResult,
)
from app.services.submission.service import (
    BlindResubmissionError,
    DuplicateSubmissionError,
    SubmissionService,
)
from app.services.workflow.nodes import UnauthorizedSubmissionError
from app.services.workflow.schemas import (
    ApplicationApprovalRequest,
    ApplicationResponse,
    ApplicationStartRequest,
    WorkflowHistoryItem,
)
from app.services.workflow.service import WorkflowService

router = APIRouter(prefix="/applications", tags=["Applications & Workflow"])


@router.post(
    "/start", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED
)
async def start_application_workflow(
    payload: ApplicationStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start or idempotently retrieve a durable application workflow."""
    service = WorkflowService()
    try:
        app = await service.start_workflow(db, current_user.id, payload)
        return ApplicationResponse(
            id=app.id,
            user_id=app.user_id,
            job_id=app.job_id,
            resume_document_id=app.resume_document_id,
            resume_version_id=app.resume_version_id,
            cover_letter_document_id=app.cover_letter_document_id,
            cover_letter_version_id=app.cover_letter_version_id,
            idempotency_key=app.idempotency_key,
            workflow_thread_id=app.workflow_thread_id,
            status=app.status,
            approval_status=app.approval_status,
            approval_notes=app.approval_notes,
            approved_at=app.approved_at,
            submission_mode=app.submission_mode,
            application_payload=app.application_payload or {},
            tracking_metadata=app.tracking_metadata or {},
            retry_count=app.retry_count,
            max_retries=app.max_retries,
            last_error=app.last_error,
            created_at=app.created_at,
            updated_at=app.updated_at,
            job_title=app.job.title if app.job else None,
            job_company=app.job.company if app.job else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=list[ApplicationResponse])
async def list_user_applications(
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all application workflows belonging to the authenticated candidate."""
    service = WorkflowService()
    apps = await service.list_applications(db, current_user.id, status_filter)
    return [
        ApplicationResponse(
            id=app.id,
            user_id=app.user_id,
            job_id=app.job_id,
            resume_document_id=app.resume_document_id,
            resume_version_id=app.resume_version_id,
            cover_letter_document_id=app.cover_letter_document_id,
            cover_letter_version_id=app.cover_letter_version_id,
            idempotency_key=app.idempotency_key,
            workflow_thread_id=app.workflow_thread_id,
            status=app.status,
            approval_status=app.approval_status,
            approval_notes=app.approval_notes,
            approved_at=app.approved_at,
            submission_mode=app.submission_mode,
            application_payload=app.application_payload or {},
            tracking_metadata=app.tracking_metadata or {},
            retry_count=app.retry_count,
            max_retries=app.max_retries,
            last_error=app.last_error,
            created_at=app.created_at,
            updated_at=app.updated_at,
            job_title=app.job.title if app.job else None,
            job_company=app.job.company if app.job else None,
        )
        for app in apps
    ]


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application_detail(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get single application details, verifying ownership."""
    service = WorkflowService()
    app = await service.get_application(db, current_user.id, application_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found or access denied",
        )

    logs = await service.get_workflow_history(db, current_user.id, application_id)
    history_items = [
        WorkflowHistoryItem(
            id=log.id,
            node_name=log.node_name,
            status=log.status,
            details=log.details or {},
            error_message=log.error_message,
            attempt_number=log.attempt_number,
            created_at=log.created_at,
        )
        for log in logs
    ]

    return ApplicationResponse(
        id=app.id,
        user_id=app.user_id,
        job_id=app.job_id,
        resume_document_id=app.resume_document_id,
        resume_version_id=app.resume_version_id,
        cover_letter_document_id=app.cover_letter_document_id,
        cover_letter_version_id=app.cover_letter_version_id,
        idempotency_key=app.idempotency_key,
        workflow_thread_id=app.workflow_thread_id,
        status=app.status,
        approval_status=app.approval_status,
        approval_notes=app.approval_notes,
        approved_at=app.approved_at,
        submission_mode=app.submission_mode,
        application_payload=app.application_payload or {},
        tracking_metadata=app.tracking_metadata or {},
        retry_count=app.retry_count,
        max_retries=app.max_retries,
        last_error=app.last_error,
        created_at=app.created_at,
        updated_at=app.updated_at,
        job_title=app.job.title if app.job else None,
        job_company=app.job.company if app.job else None,
        recent_logs=history_items,
    )


@router.post("/{application_id}/approve", response_model=ApplicationResponse)
async def approve_or_reject_application(
    application_id: int,
    payload: ApplicationApprovalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Provide human approval decision to resume the interrupted workflow."""
    service = WorkflowService()
    try:
        app = await service.resume_workflow_approval(
            db, current_user.id, application_id, payload
        )
        return ApplicationResponse(
            id=app.id,
            user_id=app.user_id,
            job_id=app.job_id,
            resume_document_id=app.resume_document_id,
            resume_version_id=app.resume_version_id,
            cover_letter_document_id=app.cover_letter_document_id,
            cover_letter_version_id=app.cover_letter_version_id,
            idempotency_key=app.idempotency_key,
            workflow_thread_id=app.workflow_thread_id,
            status=app.status,
            approval_status=app.approval_status,
            approval_notes=app.approval_notes,
            approved_at=app.approved_at,
            submission_mode=app.submission_mode,
            application_payload=app.application_payload or {},
            tracking_metadata=app.tracking_metadata or {},
            retry_count=app.retry_count,
            max_retries=app.max_retries,
            last_error=app.last_error,
            created_at=app.created_at,
            updated_at=app.updated_at,
            job_title=app.job.title if app.job else None,
            job_company=app.job.company if app.job else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{application_id}/cancel", response_model=ApplicationResponse)
async def cancel_application_workflow(
    application_id: int,
    reason: str = Query("User cancelled application workflow", alias="reason"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Explicitly cancel an application workflow."""
    service = WorkflowService()
    try:
        app = await service.cancel_workflow(db, current_user.id, application_id, reason)
        return ApplicationResponse(
            id=app.id,
            user_id=app.user_id,
            job_id=app.job_id,
            resume_document_id=app.resume_document_id,
            resume_version_id=app.resume_version_id,
            cover_letter_document_id=app.cover_letter_document_id,
            cover_letter_version_id=app.cover_letter_version_id,
            idempotency_key=app.idempotency_key,
            workflow_thread_id=app.workflow_thread_id,
            status=app.status,
            approval_status=app.approval_status,
            approval_notes=app.approval_notes,
            approved_at=app.approved_at,
            submission_mode=app.submission_mode,
            application_payload=app.application_payload or {},
            tracking_metadata=app.tracking_metadata or {},
            retry_count=app.retry_count,
            max_retries=app.max_retries,
            last_error=app.last_error,
            created_at=app.created_at,
            updated_at=app.updated_at,
            job_title=app.job.title if app.job else None,
            job_company=app.job.company if app.job else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{application_id}/history", response_model=list[WorkflowHistoryItem])
async def get_application_workflow_history(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full immutable execution timeline and step history."""
    service = WorkflowService()
    try:
        logs = await service.get_workflow_history(db, current_user.id, application_id)
        return [
            WorkflowHistoryItem(
                id=log.id,
                node_name=log.node_name,
                status=log.status,
                details=log.details or {},
                error_message=log.error_message,
                attempt_number=log.attempt_number,
                created_at=log.created_at,
            )
            for log in logs
        ]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{application_id}/package", response_model=ApplicationPackage)
async def get_application_package(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full application review package including job details, documents, and proposed answers."""
    service = SubmissionService()
    try:
        return await service.prepare_package(db, current_user.id, application_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/{application_id}/answers", response_model=ApplicationPackage)
async def update_proposed_form_answers(
    application_id: int,
    payload: FormAnswersUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Candidate edit of proposed form answers. Automatically invalidates approval if previously approved."""
    service = SubmissionService()
    try:
        return await service.update_form_answers(
            db, current_user.id, application_id, payload.form_answers
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/{application_id}/document-selection", response_model=ApplicationPackage)
async def update_document_selection(
    application_id: int,
    payload: DocumentSelectionUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Candidate update of active resume or cover letter version. Invalidates previous approval."""
    service = SubmissionService()
    try:
        return await service.update_document_selection(
            db,
            current_user.id,
            application_id,
            payload.resume_version_id,
            payload.cover_letter_version_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{application_id}/review-approval", response_model=ApplicationPackage)
async def review_and_approve_package(
    application_id: int,
    payload: ApplicationApprovalReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Explicit human approval bound to exact job, document versions, answers, and package hash."""
    service = SubmissionService()
    try:
        return await service.record_human_approval(
            db, current_user.id, application_id, payload
        )
    except ValueError as exc:
        msg = str(exc).lower()
        if "not found" in msg or "access denied" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{application_id}/submit", response_model=SubmissionResult)
async def submit_application_package(
    application_id: int,
    payload: ApplicationSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit approved application or generate manual handoff with duplicate prevention."""
    service = SubmissionService()
    try:
        return await service.submit_application(
            db, current_user.id, application_id, payload
        )
    except UnauthorizedSubmissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except DuplicateSubmissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except BlindResubmissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        )
    except ValueError as exc:
        msg = str(exc).lower()
        if "not found" in msg or "access denied" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )


@router.get(
    "/{application_id}/attempts", response_model=list[SubmissionAttemptResponse]
)
async def list_submission_attempts(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all submission attempts and audit records for this application."""
    service = SubmissionService()
    try:
        return await service.get_submission_attempts(
            db, current_user.id, application_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
