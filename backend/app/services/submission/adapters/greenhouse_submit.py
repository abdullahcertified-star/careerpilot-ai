"""Greenhouse submission adapter verifying credentials and handling confirmed receipts."""

import logging
from typing import Any

import httpx

from app.services.submission.adapters.base import SubmissionAdapter
from app.services.submission.adapters.manual_handoff import ManualHandoffAdapter
from app.services.submission.schemas import (
    ApplicationPackage,
    ProviderCapabilityInfo,
    SubmissionResult,
)

logger = logging.getLogger(__name__)


class GreenhouseSubmissionAdapter(SubmissionAdapter):
    """
    Submission adapter for Greenhouse ATS.
    Requires verified partner API credentials or applicant submission permissions.
    When credentials are missing or unauthorized, safely routes to manual handoff.
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def provider_id(self) -> str:
        return "greenhouse"

    def capabilities(self, context: dict[str, Any]) -> ProviderCapabilityInfo:
        key = self._api_key or context.get("greenhouse_api_key")
        has_creds = bool(key and key != "placeholder_greenhouse_api_key")
        return ProviderCapabilityInfo(
            provider_id="greenhouse",
            provider_name="Greenhouse Job Board & Ingestion API",
            is_direct_api=True,
            supports_submission=has_creds,
            requires_credentials=True,
            has_credentials=has_creds,
            submission_method="automated_api" if has_creds else "manual_handoff",
            handoff_reason=None
            if has_creds
            else "Greenhouse direct candidate submission requires partner API key or applicant OAuth.",
            notes="Direct candidate submission with immutable confirmation receipts when credentials are present.",
        )

    async def submit(
        self,
        package: ApplicationPackage,
        submission_key: str,
        context: dict[str, Any],
    ) -> SubmissionResult:
        # Check credentials
        key = self._api_key or context.get("greenhouse_api_key")
        mock_client = context.get("mock_http_client")
        simulate_timeout = context.get("simulate_timeout", False)
        simulate_success_receipt = context.get("simulate_success_receipt")

        if (
            not key
            and not mock_client
            and not simulate_success_receipt
            and not simulate_timeout
        ):
            # No verified credentials -> Route safely to manual handoff
            logger.info(
                "No Greenhouse submission credentials found; routing to manual handoff."
            )
            manual_adapter = ManualHandoffAdapter()
            return await manual_adapter.submit(package, submission_key, context)

        # Build Greenhouse candidate application payload
        answers = package.form_answers
        payload = {
            "first_name": answers.full_name.split()[0]
            if answers.full_name
            else "Candidate",
            "last_name": " ".join(answers.full_name.split()[1:])
            if len(answers.full_name.split()) > 1
            else "",
            "email": answers.email,
            "phone": answers.phone,
            "location": answers.location,
            "work_authorization": answers.work_authorization,
            "idempotency_key": submission_key,
            "resume_version_id": package.resume.version_id if package.resume else None,
            "cover_letter_text": package.cover_letter.formatted_text
            if package.cover_letter
            else None,
        }

        # Simulated timeout or network drop handling
        if simulate_timeout:
            logger.warning(
                "Simulated timeout during Greenhouse submission for key %s",
                submission_key,
            )
            return SubmissionResult(
                status="confirmation_pending",
                error_message="Provider submission request timed out after dispatch. Receipt confirmation is pending; blind resubmissions are barred to avoid duplicate applications.",
                blind_resubmission_prevented=True,
                response_payload={
                    "attempted_payload": payload,
                    "idempotency_key": submission_key,
                },
            )

        if simulate_success_receipt:
            return SubmissionResult(
                status="submitted",
                receipt_reference=simulate_success_receipt,
                response_payload={
                    "confirmation_id": simulate_success_receipt,
                    "provider": "greenhouse",
                    "status": "received",
                },
            )

        # Live or mock HTTP execution
        job_source_id = package.job.source_id
        target_url = f"https://boards-api.greenhouse.io/v1/boards/{package.job.company.lower().replace(' ', '')}/jobs/{job_source_id}/applications"

        client = mock_client or httpx.AsyncClient(timeout=10.0)
        try:
            resp = await client.post(
                target_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {key}",
                    "X-Idempotency-Key": submission_key,
                },
            )

            if resp.status_code in [200, 201]:
                data = resp.json() if resp.content else {}
                receipt = str(
                    data.get("id")
                    or data.get("application_id")
                    or f"GH-RECEIPT-{submission_key[:8]}"
                )
                return SubmissionResult(
                    status="submitted",
                    receipt_reference=receipt,
                    response_payload=data,
                )
            else:
                return SubmissionResult(
                    status="failed",
                    error_message=f"Greenhouse API returned error {resp.status_code}: {resp.text}",
                    response_payload={
                        "status_code": resp.status_code,
                        "text": resp.text,
                    },
                )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            # Handle uncertain outcomes using confirmation-pending status
            return SubmissionResult(
                status="confirmation_pending",
                error_message=f"Provider request timed out or network dropped after dispatch: {exc}. Confirmation pending.",
                blind_resubmission_prevented=True,
                response_payload={"error": str(exc)},
            )
        finally:
            if not mock_client:
                await client.aclose()
