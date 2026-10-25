"""Registry of submission adapters for Phase 7."""

from typing import Any

from app.services.submission.adapters.base import SubmissionAdapter
from app.services.submission.adapters.greenhouse_submit import (
    GreenhouseSubmissionAdapter,
)
from app.services.submission.adapters.manual_handoff import ManualHandoffAdapter
from app.services.submission.schemas import ProviderCapabilityInfo


class SubmissionAdapterRegistry:
    """Registry coordinating submission adapters across job providers."""

    def __init__(self) -> None:
        self._adapters: dict[str, SubmissionAdapter] = {
            "greenhouse": GreenhouseSubmissionAdapter(),
            "manual_handoff": ManualHandoffAdapter(),
        }
        self._default_adapter = ManualHandoffAdapter()

    def get_adapter(self, provider_id: str | None) -> SubmissionAdapter:
        """Resolve adapter by provider ID, defaulting to ManualHandoffAdapter for unsupported providers."""
        if not provider_id:
            return self._default_adapter
        return self._adapters.get(provider_id.lower().strip(), self._default_adapter)

    def register_adapter(self, provider_id: str, adapter: SubmissionAdapter) -> None:
        """Register or override an adapter (useful for testing)."""
        self._adapters[provider_id.lower().strip()] = adapter

    def get_capability(
        self, provider_id: str | None, context: dict[str, Any]
    ) -> ProviderCapabilityInfo:
        """Query capabilities for target provider."""
        adapter = self.get_adapter(provider_id)
        return adapter.capabilities(context)


submission_registry = SubmissionAdapterRegistry()
