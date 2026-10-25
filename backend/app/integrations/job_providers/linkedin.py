"""LinkedIn Link-First Job Provider Adapter."""

import urllib.parse
from typing import Any, Optional

from app.integrations.job_providers.base import JobProvider
from app.schemas.job import JobSearchQuery, JobSearchResult, NormalizedJob, ProviderCapabilities


class LinkedInAdapter(JobProvider):
    """
    Link-First adapter for LinkedIn Jobs.
    Generates structured, compliant portal search URLs for the candidate's browser session.
    Direct programmatic scraping without LinkedIn Enterprise Partner API authorization is prohibited.
    """

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id="linkedin",
            name="LinkedIn Jobs (Link-First)",
            description=(
                "Link-first provider. Generates authenticated portal search links with pre-filled filters. "
                "Direct API access or scraping is prohibited under LinkedIn terms without Enterprise Partner API authorization."
            ),
            integration_status="link_first",
            supports_search=True,
            supports_details=False,
            supports_url_import=False,
            is_direct_api=False,
            link_first_only=True,
            rate_limit_rpm=120,
            documentation_url="https://www.linkedin.com/help/linkedin/answer/a544943",
            external_search_template="https://www.linkedin.com/jobs/search/?keywords={keywords}&location={location}",
        )

    def generate_search_url(self, query: JobSearchQuery) -> str:
        """Constructs a parameterized LinkedIn job search URL."""
        base = "https://www.linkedin.com/jobs/search/?"
        params = []
        if query.query:
            params.append(f"keywords={urllib.parse.quote_plus(query.query)}")
        if query.location:
            params.append(f"location={urllib.parse.quote_plus(query.location)}")
        if query.work_mode:
            wm = query.work_mode.lower()
            if wm == "remote":
                params.append("f_WT=2")
            elif wm == "hybrid":
                params.append("f_WT=3")
            elif wm == "onsite":
                params.append("f_WT=1")

        return base + "&".join(params) if params else "https://www.linkedin.com/jobs/"

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        search_url = self.generate_search_url(query)
        return JobSearchResult(
            jobs=[],
            total_count=0,
            page=query.page,
            page_size=query.page_size,
            has_more=False,
            provider_id="linkedin",
            provider_status="link_first",
            external_search_url=search_url,
            warnings=[
                "LinkedIn integration operates in Link-First mode. "
                "Click 'Open in LinkedIn' to view live results in your authenticated browser session. "
                "You can import individual job URLs directly into CareerPilot using the 'Import URL' tool."
            ],
        )

    async def fetch_details(
        self, job_id: str, board_token: Optional[str] = None
    ) -> Optional[NormalizedJob]:
        return None

    def normalize(self, raw_data: Any, context: Optional[dict] = None) -> NormalizedJob:
        raise NotImplementedError("LinkedIn does not support direct raw data normalization in link-first mode.")
