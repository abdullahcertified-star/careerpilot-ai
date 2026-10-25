from app.core.config import settings
from app.integrations.llm import LLMClientProvider


def test_settings_load() -> None:
    """Validate core settings load default values safely."""
    assert settings.APP_NAME == "CareerPilot AI"
    assert settings.PORT == 8000
    assert settings.SECRET_KEY is not None


def test_llm_provider_fallback() -> None:
    """Validate LLM client fallback mechanism when keys are placeholder values."""
    provider = LLMClientProvider()
    assert provider.is_configured() is False
    mock_out = provider.generate_mock_response("Analyze job description")
    assert mock_out["mode"] == "mock"
    assert "CareerPilot AI" in mock_out["response"]
