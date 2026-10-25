"""Indeed Link-First Job Provider Adapter."""

import urllib.parse
from typing import Any, Optional

from app.integrations.job_providers.base import JobProvider
from app.schemas.job import JobSearchQuery, JobSearchResult, NormalizedJob, ProviderCapabilities


class IndeedAdapter(JobProvider):
    """
    Link-First adapter for Indeed.
    Generates structured, compliant portal search URLs for the candidate's browser session.
    Direct job scraping without an official Indeed Publisher / XML Partner agreement is prohibited.
    """

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id="indeed",
            name="Indeed (Link-First)",
            description=(
                "Link-first provider. Generates parameterized Indeed search links. "
                "Automated ingestion requires an authorized Indeed Publisher or XML Partner agreement."
            ),
            integration_status="link_first",
            supports_search=True,
            supports_details=False,
            supports_url_import=False,
            is_direct_api=False,
            link_first_only=True,
            rate_limit_rpm=120,
            documentation_url="https://developer.indeed.com/",
            external_search_template="https://www.indeed.com/jobs?q={keywords}&l={location}",
        )

    def generate_search_url(self, query: JobSearchQuery) -> str:
        """Constructs a parameterized Indeed job search URL."""
        base = "https://www.indeed.com/jobs?"
        params = []
        if query.query:
            params.append(f"q={urllib.parse.quote_plus(query.query)}")
        if query.location:
            params.append(f"l={urllib.parse.quote_plus(query.location)}")
        if query.work_mode and query.work_mode.lower() == "remote":
            params.append("sc=0kf%3Aattr%28DS3S6%29%3B")

        return base + "&".join(params) if params else "https://www.indeed.com/jobs"

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        search_url = self.generate_search_url(query)
        return JobSearchResult(
            jobs=[],
            total_count=0,
            page=query.page,
            page_size=query.page_size,
            has_more=False,
            provider_id="indeed",
            provider_status="link_first",
            external_search_url=search_url,
            warnings=[
                "Indeed integration operates in Link-First mode. "
                "Click 'Open in Indeed' to review live matching jobs. "
                "Copy any interesting job URL and paste it into CareerPilot's 'Import URL' tool to ingest and track it."
            ],
        )

    async def fetch_details(
        self, job_id: str, board_token: Optional[str] = None
    ) -> Optional[NormalizedJob]:
        return None

    def normalize(self, raw_data: Any, context: Optional[dict] = None) -> NormalizedJob:
        raise NotImplementedError("Indeed does not support direct raw data normalization in link-first mode.")
