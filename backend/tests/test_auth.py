import uuid
import pytest
from httpx import AsyncClient


def random_email() -> str:
    return f"user_{uuid.uuid4().hex[:8]}@example.com"


@pytest.mark.asyncio
async def test_registration_success(async_client: AsyncClient) -> None:
    """Registration succeeds with valid input, returning auth token and user."""
    email = random_email()
    payload = {
        "email": email,
        "password": "StrongPassword123!",
        "full_name": "Test Candidate",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "token" in data
    assert data["user"]["email"] == email
    assert data["user"]["full_name"] == "Test Candidate"
    assert "careerpilot_session" in response.cookies


@pytest.mark.asyncio
async def test_duplicate_email_registration_rejected(async_client: AsyncClient) -> None:
    """Duplicate email registration is rejected with 400 Bad Request."""
    email = random_email()
    payload = {
        "email": email,
        "password": "StrongPassword123!",
        "full_name": "Test Candidate",
    }
    # First registration
    resp1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    # Second registration with same email
    resp2 = await async_client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 400
    assert "already exists" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_malformed_inputs_rejected(async_client: AsyncClient) -> None:
    """Malformed inputs (short password, invalid email, empty name) are rejected with 422."""
    # Password too short (<8 chars)
    resp1 = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "valid@example.com", "password": "short", "full_name": "Valid Name"},
    )
    assert resp1.status_code == 422

    # Invalid email format
    resp2 = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "ValidPassword123!", "full_name": "Valid Name"},
    )
    assert resp2.status_code == 422

    # Name too short
    resp3 = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "valid2@example.com", "password": "ValidPassword123!", "full_name": "A"},
    )
    assert resp3.status_code == 422


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient) -> None:
    """Login succeeds with valid credentials."""
    email = random_email()
    password = "MySecurePassword123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Candidate One"},
    )

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "token" in data
    assert data["user"]["email"] == email


@pytest.mark.asyncio
async def test_invalid_login_rejected_without_revealing_details(async_client: AsyncClient) -> None:
    """Invalid login is rejected with generic message regardless of whether email exists."""
    email = random_email()
    # Case 1: Email does not exist
    resp_no_user = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "AnyPassword123!"},
    )
    assert resp_no_user.status_code == 401
    assert resp_no_user.json()["detail"] == "Invalid email or password."

    # Case 2: Email exists, wrong password
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "CorrectPassword123!", "full_name": "Candidate"},
    )
    resp_wrong_pwd = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword999!"},
    )
    assert resp_wrong_pwd.status_code == 401
    assert resp_wrong_pwd.json()["detail"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_unauthenticated_requests_return_401(async_client: AsyncClient) -> None:
    """Unauthenticated requests to protected endpoints return 401 Unauthorized."""
    resp1 = await async_client.get("/api/v1/auth/me")
    assert resp1.status_code == 401

    resp2 = await async_client.get("/api/v1/profile/me")
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalidates_session(async_client: AsyncClient) -> None:
    """Logout invalidates the session token in database and denies further access."""
    email = random_email()
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePassword123!", "full_name": "Logout Tester"},
    )
    token = reg_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token works
    me_resp1 = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_resp1.status_code == 200

    # Logout
    logout_resp = await async_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # Verify token is now rejected
    me_resp2 = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_resp2.status_code == 401
