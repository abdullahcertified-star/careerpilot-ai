"""Workflow orchestration service managing execution, restarts, approval, and persistence."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import (
    DocumentVersion,
    GeneratedDocument,
    JobApplication,
    JobPosting,
    WorkflowExecutionLog,
)
from app.services.workflow.checkpointer import get_durable_checkpointer, get_sync_checkpointer
from app.services.workflow.graph import compile_workflow_graph
from app.services.workflow.redactor import RedactingLangSmithTracer
from app.services.workflow.schemas import (
    ApplicationApprovalRequest,
    ApplicationResponse,
    ApplicationStartRequest,
    WorkflowHistoryItem,
    WorkflowState,
)

logger = logging.getLogger(__name__)


class WorkflowService:
    """Service orchestrating durable LangGraph job application workflows."""

    def __init__(self, checkpointer: Optional[BaseCheckpointSaver[Any]] = None):
        self._custom_checkpointer = checkpointer

    async def _get_checkpointer(self) -> BaseCheckpointSaver[Any]:
        if self._custom_checkpointer:
            return self._custom_checkpointer
        try:
            return await get_durable_checkpointer()
        except Exception as exc:
            logger.warning("Falling back to synchronous memory checkpointer: %s", exc)
            return get_sync_checkpointer()

    async def start_workflow(
        self,
        session: AsyncSession,
        user_id: int,
        request: ApplicationStartRequest,
    ) -> JobApplication:
        """Initiate or idempotently resume an application workflow."""
        # 1. Idempotency Check: if key provided, check for existing application
        idempotency_key = request.idempotency_key or f"user:{user_id}:job:{request.job_id or request.job_url}:{uuid4().hex}"
        stmt = (
            select(JobApplication)
            .options(selectinload(JobApplication.job), selectinload(JobApplication.execution_logs))
            .where(JobApplication.user_id == user_id, JobApplication.idempotency_key == idempotency_key)
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.info("Idempotent hit for application key %s (id=%s)", idempotency_key, existing.id)
            return existing

        # 2. Create durable JobApplication record
        thread_id = f"thread_{user_id}_{uuid4().hex[:12]}"
        application = JobApplication(
            user_id=user_id,
            job_id=request.job_id,
            idempotency_key=idempotency_key,
            workflow_thread_id=thread_id,
            status="pending",
            approval_status="pending",
            submission_mode=request.submission_mode or "manual_handoff",
            application_payload={},
            tracking_metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(application)
        await session.commit()
        await session.refresh(application)

        # 3. Setup LangGraph state and checkpointer
        checkpointer = await self._get_checkpointer()
        graph = compile_workflow_graph(checkpointer)

        initial_state: WorkflowState = {
            "thread_id": thread_id,
            "user_id": user_id,
            "application_id": application.id,
            "idempotency_key": idempotency_key,
            "raw_job_url": request.job_url,
            "provider_id": request.provider_id,
            "source_id": request.source_id,
            "job_id": request.job_id,
            "template_id": request.template_id or "modern",
            "custom_instructions": request.custom_instructions,
            "submission_mode": request.submission_mode or "manual_handoff",
            "retry_count": 0,
            "max_retries": 3,
            "status": "pending",
        }

        # 4. Execute workflow with redaction tracer
        tracer = RedactingLangSmithTracer(
            run_tags=["careerpilot", f"user_{user_id}", f"app_{application.id}"],
            metadata={"idempotency_key": idempotency_key, "submission_mode": application.submission_mode},
        )

        config = cast(
            RunnableConfig,
            {
                "configurable": {"thread_id": thread_id},
                "callbacks": [tracer],
            },
        )

        try:
            # Invoking graph will run up to the human_approval interrupt gate
            final_state = await graph.ainvoke(initial_state, config=config)
            if isinstance(final_state, dict):
                if final_state.get("status"):
                    application.status = final_state["status"]
                if final_state.get("last_error"):
                    application.last_error = final_state["last_error"]
                if final_state.get("retry_count"):
                    application.retry_count = final_state["retry_count"]
                await session.commit()
        except Exception as exc:
            # Log failure but preserve durable application record
            logger.error("Workflow thread %s encountered error: %s", thread_id, exc)
            application.last_error = str(exc)
            application.status = "failed"
            await session.commit()

        # Reload updated application state
        await session.refresh(application)
        return application

    async def resume_workflow_approval(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
        approval_request: ApplicationApprovalRequest,
    ) -> JobApplication:
        """Resume an interrupted workflow after human approval or rejection."""
        stmt = (
            select(JobApplication)
            .options(selectinload(JobApplication.job), selectinload(JobApplication.execution_logs))
            .where(JobApplication.id == application_id, JobApplication.user_id == user_id)
        )
        application = (await session.execute(stmt)).scalar_one_or_none()
        if not application:
            raise ValueError(f"Application {application_id} not found or access denied")

        # Check if already terminated
        if application.status in ["submitted", "manual_handoff", "cancelled", "rejected"]:
            return application

        thread_id = application.workflow_thread_id
        checkpointer = await self._get_checkpointer()
        graph = compile_workflow_graph(checkpointer)

        decision = {
            "approved": approval_request.approved,
            "notes": approval_request.notes,
        }

        # Update application state in database
        application.approval_status = "approved" if approval_request.approved else "rejected"
        application.approval_notes = approval_request.notes
        if approval_request.approved:
            application.approved_at = datetime.now(timezone.utc)
        await session.commit()

        tracer = RedactingLangSmithTracer(
            run_tags=["careerpilot", f"user_{user_id}", f"app_{application.id}", "resume_approval"],
        )
        config = cast(
            RunnableConfig,
            {
                "configurable": {"thread_id": thread_id},
                "callbacks": [tracer],
            },
        )

        try:
            # Resume graph with Command(resume=decision)
            await graph.ainvoke(Command(resume=decision), config=config)
        except Exception as exc:
            logger.error("Resume workflow failed for thread %s: %s", thread_id, exc)
            application.last_error = str(exc)
            await session.commit()

        await session.refresh(application)
        return application

    async def cancel_workflow(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
        reason: str = "User cancelled workflow",
    ) -> JobApplication:
        """Explicitly cancel an active application workflow."""
        stmt = (
            select(JobApplication)
            .options(selectinload(JobApplication.job), selectinload(JobApplication.execution_logs))
            .where(JobApplication.id == application_id, JobApplication.user_id == user_id)
        )
        application = (await session.execute(stmt)).scalar_one_or_none()
        if not application:
            raise ValueError(f"Application {application_id} not found or access denied")

        application.status = "cancelled"
        application.approval_status = "rejected"
        application.approval_notes = reason
        await session.commit()

        # Record cancellation log
        log = WorkflowExecutionLog(
            application_id=application.id,
            thread_id=application.workflow_thread_id,
            node_name="cancellation",
            status="completed",
            details={"reason": reason},
            created_at=datetime.now(timezone.utc),
        )
        session.add(log)
        await session.commit()
        await session.refresh(application)
        return application

    async def invalidate_approval_on_document_edit(
        self,
        session: AsyncSession,
        user_id: int,
        document_id: int,
        new_version_id: int,
    ) -> List[int]:
        """Invalidate human approval on any application linked to a modified document."""
        # Find applications using this document that were previously approved
        stmt = select(JobApplication).where(
            JobApplication.user_id == user_id,
            (JobApplication.resume_document_id == document_id) | (JobApplication.cover_letter_document_id == document_id),
            JobApplication.approval_status == "approved",
        )
        apps = (await session.execute(stmt)).scalars().all()
        invalidated_ids: List[int] = []

        for app in apps:
            app.approval_status = "invalidated"
            app.status = "awaiting_approval"
            app.approval_notes = f"Approval invalidated due to document revision (Version ID {new_version_id})"
            # Update active version reference if applicable
            if app.resume_document_id == document_id:
                app.resume_version_id = new_version_id
            if app.cover_letter_document_id == document_id:
                app.cover_letter_version_id = new_version_id

            session.add(
                WorkflowExecutionLog(
                    application_id=app.id,
                    thread_id=app.workflow_thread_id,
                    node_name="approval_invalidation",
                    status="completed",
                    details={"document_id": document_id, "new_version_id": new_version_id},
                    error_message="Document edited after approval; re-review required",
                    created_at=datetime.now(timezone.utc),
                )
            )
            invalidated_ids.append(app.id)

        if invalidated_ids:
            await session.commit()
            logger.info("Invalidated approval for applications %s due to document edit", invalidated_ids)

        return invalidated_ids

    async def list_applications(
        self,
        session: AsyncSession,
        user_id: int,
        status: Optional[str] = None,
    ) -> List[JobApplication]:
        """List user applications with optional status filter."""
        stmt = (
            select(JobApplication)
            .options(selectinload(JobApplication.job), selectinload(JobApplication.execution_logs))
            .where(JobApplication.user_id == user_id)
            .order_by(JobApplication.updated_at.desc())
        )
        if status:
            stmt = stmt.where(JobApplication.status == status)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def get_application(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
    ) -> Optional[JobApplication]:
        """Get application detail verifying ownership."""
        stmt = (
            select(JobApplication)
            .options(selectinload(JobApplication.job), selectinload(JobApplication.execution_logs))
            .where(JobApplication.id == application_id, JobApplication.user_id == user_id)
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_workflow_history(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
    ) -> List[WorkflowExecutionLog]:
        """Retrieve audit timeline for an application verifying ownership."""
        # Ownership check
        app = await self.get_application(session, user_id, application_id)
        if not app:
            raise ValueError(f"Application {application_id} not found or access denied")

        stmt = (
            select(WorkflowExecutionLog)
            .where(WorkflowExecutionLog.application_id == application_id)
            .order_by(WorkflowExecutionLog.created_at.asc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())
