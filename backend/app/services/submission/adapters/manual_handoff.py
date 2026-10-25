"""Manual handoff adapter for unsupported sites and privacy-first application submission."""

from datetime import UTC, datetime
from typing import Any

from app.services.submission.adapters.base import SubmissionAdapter
from app.services.submission.schemas import (
    ApplicationPackage,
    LabeledAnswerItem,
    ManualHandoffPacket,
    ProviderCapabilityInfo,
    SubmissionResult,
)


class ManualHandoffAdapter(SubmissionAdapter):
    """
    Standard manual handoff adapter.
    Prepares a clean copy-paste package and direct link to the original job requisition
    for unsupported ATS systems, sites without API credentials, or privacy-conscious users.
    """

    def provider_id(self) -> str:
        return "manual_handoff"

    def capabilities(self, context: dict[str, Any]) -> ProviderCapabilityInfo:
        return ProviderCapabilityInfo(
            provider_id="manual_handoff",
            provider_name="Manual Handoff",
            is_direct_api=False,
            supports_submission=False,
            requires_credentials=False,
            has_credentials=False,
            submission_method="manual_handoff",
            handoff_reason="Direct API submission not supported or credentials not configured for this portal.",
            notes="Generates verified application packet with downloadable resume and pre-formatted answers.",
        )

    async def submit(
        self,
        package: ApplicationPackage,
        submission_key: str,
        context: dict[str, Any],
    ) -> SubmissionResult:
        answers = package.form_answers
        labeled_items: list[LabeledAnswerItem] = [
            LabeledAnswerItem(
                field_key="full_name",
                label="Full Legal Name",
                value=answers.full_name,
            ),
            LabeledAnswerItem(
                field_key="email",
                label="Primary Contact Email",
                value=answers.email,
            ),
            LabeledAnswerItem(
                field_key="phone",
                label="Contact Phone",
                value=answers.phone or "Not provided in profile",
            ),
            LabeledAnswerItem(
                field_key="location",
                label="Location / Residence",
                value=answers.location or "Remote / Flexible",
            ),
            LabeledAnswerItem(
                field_key="work_authorization",
                label="Work Authorization Status",
                value=answers.work_authorization,
                help_text="Verified from candidate profile facts.",
            ),
            LabeledAnswerItem(
                field_key="requires_sponsorship",
                label="Visa Sponsorship Required",
                value="Yes" if answers.requires_sponsorship else "No",
            ),
            LabeledAnswerItem(
                field_key="notice_period",
                label="Availability / Notice Period",
                value=answers.notice_period,
            ),
        ]

        if answers.linkedin_url:
            labeled_items.append(
                LabeledAnswerItem(
                    field_key="linkedin_url",
                    label="LinkedIn Profile",
                    value=answers.linkedin_url,
                )
            )
        if answers.github_url:
            labeled_items.append(
                LabeledAnswerItem(
                    field_key="github_url",
                    label="GitHub Profile",
                    value=answers.github_url,
                )
            )
        if answers.portfolio_url:
            labeled_items.append(
                LabeledAnswerItem(
                    field_key="portfolio_url",
                    label="Portfolio / Website",
                    value=answers.portfolio_url,
                )
            )

        # Highlight sensitive fields that require direct candidate completion
        for s_field in answers.sensitive_fields_requiring_manual_input:
            labeled_items.append(
                LabeledAnswerItem(
                    field_key=s_field,
                    label=s_field.replace("_", " ").title(),
                    value="[MANUAL COMPLETION REQUIRED]",
                    is_sensitive=True,
                    help_text="CareerPilot AI never guesses sensitive PII or bypasses security/MFA controls.",
                )
            )

        instructions = [
            f"1. Open the employer application URL: {package.original_application_url}",
            "2. Upload your approved resume file (downloadable via the Documents tab).",
            "3. If requested, paste your tailored cover letter from this review packet.",
            "4. Copy and paste the verified form answers below into the employer form.",
            "5. Review and complete any sensitive employer questionnaire items (e.g. EEOC, live CAPTCHA) directly.",
            "6. Submit on the employer site and retain your confirmation email.",
        ]

        cover_text = (
            package.cover_letter.formatted_text if package.cover_letter else None
        )

        handoff_packet = ManualHandoffPacket(
            application_id=package.application_id,
            job_title=package.job.title,
            company=package.job.company,
            original_application_url=package.original_application_url,
            resume_document_id=package.resume.document_id if package.resume else None,
            resume_version_id=package.resume.version_id if package.resume else None,
            cover_letter_document_id=package.cover_letter.document_id
            if package.cover_letter
            else None,
            cover_letter_version_id=package.cover_letter.version_id
            if package.cover_letter
            else None,
            cover_letter_text=cover_text,
            labeled_answers=labeled_items,
            instructions=instructions,
            generated_at=datetime.now(UTC),
        )

        return SubmissionResult(
            status="manual_handoff",
            receipt_reference=f"HANDOFF-{package.application_id}-{submission_key[:8]}",
            response_payload=handoff_packet.model_dump(mode="json"),
            handoff_packet=handoff_packet,
        )
