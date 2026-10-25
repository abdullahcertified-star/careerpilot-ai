"""LLM client interface and safe local development fallback."""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMClientProvider:
    """Safe LLM client provider that supports local mock fallback when API keys are unset."""

    def __init__(self) -> None:
        self.openai_key = settings.OPENAI_API_KEY
        self.anthropic_key = settings.ANTHROPIC_API_KEY
        self.gemini_key = settings.GEMINI_API_KEY

    def is_configured(self) -> bool:
        """Check if any real LLM API key has been provided."""
        return (
            self.openai_key not in ("placeholder_openai_api_key", "", None)
            or self.anthropic_key not in ("placeholder_anthropic_api_key", "", None)
            or self.gemini_key not in ("placeholder_gemini_api_key", "", None)
        )

    def generate_mock_response(self, prompt: str) -> dict[str, Any]:
        """Provide deterministic mock response for testing and offline development."""
        return {
            "mode": "mock",
            "prompt_length": len(prompt),
            "response": "CareerPilot AI local simulation response: candidate matches 85% of job requirements.",
        }
