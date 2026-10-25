import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient) -> None:
    """Validate root endpoint response format and status code."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert data["service"] == "CareerPilot AI"
    assert "environment" in data


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient) -> None:
    """Validate health check endpoint returns 200 and expected schema."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "CareerPilot AI"
    assert "version" in data
