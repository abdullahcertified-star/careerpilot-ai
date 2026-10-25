import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.rate_limit import rate_limiter
from app.main import app as fastapi_app
from app.models.entities import User


@pytest.mark.asyncio
async def test_database_health_endpoint(async_client: AsyncClient) -> None:
    """Database health check returns 200 with connection details."""
    response = await async_client.get("/api/v1/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert "driver" in data


@pytest.mark.asyncio
async def test_rate_limiting_enforcement(async_client: AsyncClient) -> None:
    """Rate limiting blocks rapid repeated requests with HTTP 429."""
    key = "auth:127.0.0.1"
    # Artificially populate rate limiter to simulate threshold hit
    rate_limiter.requests[key] = [9999999999.0] * 25

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "Password123!"},
    )
    assert response.status_code == 429
    assert "Too many authentication attempts" in response.json()["detail"]

    # Reset limiter for subsequent tests
    rate_limiter.requests[key] = []


@pytest.mark.asyncio
async def test_records_persist_across_client_and_app_lifecycle() -> None:
    """Verify persisted database records remain across API client restarts."""
    # Ensure fresh rate limit state
    rate_limiter.requests.clear()

    test_email = f"persist_{uuid.uuid4().hex[:8]}@example.com"
    password = "PersistPassword123!"

    # 1. Use client instance A to register
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://testserver") as client_a:
        resp = await client_a.post(
            "/api/v1/auth/register",
            json={"email": test_email, "password": password, "full_name": "Persist User"},
        )
        assert resp.status_code == 201
        user_id = resp.json()["user"]["id"]

    # 2. Directly verify in database engine
    async with async_session_factory() as session:
        stmt = select(User).where(User.id == user_id)
        persisted_user = (await session.execute(stmt)).scalar_one_or_none()
        assert persisted_user is not None
        assert persisted_user.email == test_email

    # 3. Simulate completely new client instance B connecting later
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://testserver") as client_b:
        login_resp = await client_b.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": password},
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["user"]["id"] == user_id
