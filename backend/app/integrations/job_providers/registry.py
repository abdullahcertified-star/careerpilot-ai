"""Registry managing job provider adapters and dispatching searches."""

import logging
from typing import Dict, List, Optional

from app.integrations.job_providers.base import JobProvider
from app.integrations.job_providers.greenhouse import GreenhouseAdapter
from app.integrations.job_providers.indeed import IndeedAdapter
from app.integrations.job_providers.linkedin import LinkedInAdapter
from app.integrations.job_providers.manual_import import ManualImportAdapter
from app.schemas.job import JobSearchQuery, JobSearchResult, ProviderCapabilities

logger = logging.getLogger(__name__)


class JobProviderRegistry:
    """Manages active job discovery providers and coordinates execution with error isolation."""

    def __init__(self) -> None:
        self._providers: Dict[str, JobProvider] = {}
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        self.register(GreenhouseAdapter())
        self.register(LinkedInAdapter())
        self.register(IndeedAdapter())
        self.register(ManualImportAdapter())

    def register(self, provider: JobProvider) -> None:
        caps = provider.capabilities()
        self._providers[caps.provider_id] = provider

    def get_provider(self, provider_id: str) -> Optional[JobProvider]:
        return self._providers.get(provider_id)

    def list_capabilities(self) -> List[ProviderCapabilities]:
        return [provider.capabilities() for provider in self._providers.values()]

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        """
        Executes job search across selected or all active providers with error isolation.
        A failure in one provider will never crash the search or prevent other providers from returning results.
        """
        target_provider_id = query.provider_id or "greenhouse"

        if target_provider_id != "all":
            provider = self._providers.get(target_provider_id)
            if not provider:
                return JobSearchResult(
                    jobs=[],
                    total_count=0,
                    page=query.page,
                    page_size=query.page_size,
                    has_more=False,
                    provider_id=target_provider_id,
                    provider_status="unknown",
                    warnings=[f"Provider '{target_provider_id}' is not registered or supported."],
                )

            try:
                return await provider.search(query)
            except Exception as exc:
                logger.error("Provider '%s' search failed: %s", target_provider_id, exc, exc_info=True)
                return JobSearchResult(
                    jobs=[],
                    total_count=0,
                    page=query.page,
                    page_size=query.page_size,
                    has_more=False,
                    provider_id=target_provider_id,
                    provider_status="error",
                    warnings=[f"Search on provider '{target_provider_id}' encountered an issue: {str(exc)}"],
                )

        # "all" selected: Query direct APIs and gather link-first options
        all_jobs = []
        all_warnings: List[str] = []
        external_urls: Dict[str, str] = {}

        # 1. Query Greenhouse (direct API)
        greenhouse = self._providers.get("greenhouse")
        if greenhouse:
            try:
                gh_result = await greenhouse.search(query)
                all_jobs.extend(gh_result.jobs)
                all_warnings.extend(gh_result.warnings)
            except Exception as exc:
                logger.warning("Greenhouse search failed during multi-provider dispatch: %s", exc)
                all_warnings.append(f"Greenhouse direct API error: {str(exc)}")

        # 2. Gather Link-First portals for candidate convenience
        for pid in ("linkedin", "indeed"):
            adapter = self._providers.get(pid)
            if adapter and isinstance(adapter, (LinkedInAdapter, IndeedAdapter)):
                try:
                    res = await adapter.search(query)
                    if res.external_search_url:
                        external_urls[pid] = res.external_search_url
                except Exception as exc:
                    logger.debug("Failed to generate link for %s: %s", pid, exc)

        total_count = len(all_jobs)
        return JobSearchResult(
            jobs=all_jobs,
            total_count=total_count,
            page=query.page,
            page_size=query.page_size,
            has_more=False,
            provider_id="all",
            provider_status="multi_provider",
            warnings=all_warnings,
        )


# Global registry singleton
registry = JobProviderRegistry()
