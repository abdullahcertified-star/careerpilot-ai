"""Abstract base class for all job provider adapters."""

from abc import ABC, abstractmethod
from typing import Any, Optional
from app.schemas.job import JobSearchQuery, JobSearchResult, NormalizedJob, ProviderCapabilities


class JobProvider(ABC):
    """Common interface for job discovery providers."""

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Reports provider capabilities, integration status, and limits."""
        pass

    @abstractmethod
    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        """Executes a search query against the provider."""
        pass

    @abstractmethod
    async def fetch_details(
        self, job_id: str, board_token: Optional[str] = None
    ) -> Optional[NormalizedJob]:
        """Fetches full job details for a specific job ID."""
        pass

    @abstractmethod
    def normalize(self, raw_data: Any, context: Optional[dict] = None) -> NormalizedJob:
        """Normalizes provider-specific raw payload into canonical NormalizedJob."""
        pass
