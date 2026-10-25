"""Job providers integration package."""

from app.integrations.job_providers.base import JobProvider
from app.integrations.job_providers.greenhouse import GreenhouseAdapter
from app.integrations.job_providers.indeed import IndeedAdapter
from app.integrations.job_providers.linkedin import LinkedInAdapter
from app.integrations.job_providers.manual_import import ManualImportAdapter
from app.integrations.job_providers.registry import JobProviderRegistry, registry

__all__ = [
    "JobProvider",
    "GreenhouseAdapter",
    "LinkedInAdapter",
    "IndeedAdapter",
    "ManualImportAdapter",
    "JobProviderRegistry",
    "registry",
]
