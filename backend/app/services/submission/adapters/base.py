"""Abstract base class for Phase 7 application submission adapters."""

from abc import ABC, abstractmethod
from typing import Any

from app.services.submission.schemas import (
    ApplicationPackage,
    ProviderCapabilityInfo,
    SubmissionResult,
)


class SubmissionAdapter(ABC):
    """Common interface for external submission and manual handoff adapters."""

    @abstractmethod
    def provider_id(self) -> str:
        """Identifier of the target provider."""
        pass

    @abstractmethod
    def capabilities(self, context: dict[str, Any]) -> ProviderCapabilityInfo:
        """Report submission capabilities based on credentials and permission."""
        pass

    @abstractmethod
    async def submit(
        self,
        package: ApplicationPackage,
        submission_key: str,
        context: dict[str, Any],
    ) -> SubmissionResult:
        """Execute submission or produce manual handoff packet."""
        pass
