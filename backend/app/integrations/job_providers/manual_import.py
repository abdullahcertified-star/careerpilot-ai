"""Manual URL job import adapter with SSRF protection and HTML extraction."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from app.integrations.job_providers.base import JobProvider
from app.schemas.job import JobSearchQuery, JobSearchResult, NormalizedJob, ProviderCapabilities
from app.services.html_sanitizer import extract_job_from_html
from app.services.ssrf_protector import safe_fetch_url


class ManualImportAdapter(JobProvider):
    """Adapter for importing and parsing individual job listings from public web URLs."""

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id="manual_import",
            name="Manual URL Import",
            description="Secure job import engine supporting public company career pages and ATS URLs with SSRF protection.",
            integration_status="verified_secure_import",
            supports_search=False,
            supports_details=False,
            supports_url_import=True,
            is_direct_api=False,
            link_first_only=False,
            rate_limit_rpm=30,
        )

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        return JobSearchResult(
            jobs=[],
            total_count=0,
            page=1,
            page_size=20,
            has_more=False,
            provider_id="manual_import",
            provider_status="verified_secure_import",
        )

    async def fetch_details(
        self, job_id: str, board_token: Optional[str] = None
    ) -> Optional[NormalizedJob]:
        return None

    def normalize(self, raw_data: Any, context: Optional[dict] = None) -> NormalizedJob:
        return raw_data  # Already normalized in import_from_url

    async def import_from_url(self, raw_url: str) -> NormalizedJob:
        """
        Safely fetches external job page, validates network destination,
        extracts structured metadata, and normalizes into NormalizedJob.
        """
        final_url, html_content, _ = await safe_fetch_url(raw_url)
        extracted = extract_job_from_html(html_content, base_url=final_url)

        # Deterministic source_id based on SHA-256 of canonical URL
        source_id = hashlib.sha256(extracted["canonical_url"].encode("utf-8")).hexdigest()[:16]

        return NormalizedJob(
            source="manual_import",
            source_id=source_id,
            canonical_url=extracted["canonical_url"],
            title=extracted["title"],
            company=extracted["company"],
            description=extracted["description"],
            location=extracted["location"],
            work_mode=extracted["work_mode"],
            employment_type=extracted["employment_type"],
            posted_at=datetime.now(timezone.utc),
            retrieved_at=datetime.now(timezone.utc),
            raw_metadata={"original_input_url": raw_url, "final_url": final_url},
        )
