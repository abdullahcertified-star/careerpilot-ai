from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_SQLITE_PATH = (BASE_DIR / "careerpilot_dev.db").as_posix()


class Settings(BaseSettings):
    """Application settings with environment variable fallback and validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "CareerPilot AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

    SECRET_KEY: str = "development-secret-key-change-in-production-min-32-chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ALGORITHM: str = "HS256"

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "careerpilot_db"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH}"
    POSTGRES_DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/careerpilot_db"

    SESSION_COOKIE_NAME: str = "careerpilot_session"
    SESSION_MAX_AGE_SECONDS: int = 86400 * 7  # 7 days
    RATE_LIMIT_AUTH_PER_MINUTE: int = 20
    RATE_LIMIT_GENERAL_PER_MINUTE: int = 120

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"

    OPENAI_API_KEY: str = "placeholder_openai_api_key"
    ANTHROPIC_API_KEY: str = "placeholder_anthropic_api_key"
    GEMINI_API_KEY: str = "placeholder_gemini_api_key"
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = "placeholder_langsmith_api_key"
    LANGSMITH_PROJECT: str = "careerpilot-ai-dev"


settings = Settings()
