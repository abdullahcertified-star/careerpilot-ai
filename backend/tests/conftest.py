from collections.abc import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient

import app.models  # noqa: F401
from app.core.database import Base, engine
from app.core.rate_limit import rate_limiter
from app.main import app as fastapi_app


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """Clear in-memory rate limiter between tests to prevent cross-test throttle spillover."""
    rate_limiter.requests.clear()


@pytest.fixture(autouse=True, scope="session")
async def setup_test_database() -> AsyncGenerator[None, None]:
    """Ensure database tables exist for all test runs."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture for FastAPI test execution."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://testserver",
    ) as client:
        yield client
