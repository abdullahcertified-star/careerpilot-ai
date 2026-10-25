import uuid
import pytest
from httpx import AsyncClient


def make_email() -> str:
    return f"cand_{uuid.uuid4().hex[:8]}@example.com"


@pytest.mark.asyncio
async def test_candidate_profile_flow_and_ownership(async_client: AsyncClient) -> None:
    """Validate profile update and strict ownership enforcement between User A and User B."""
    # 1. Register User A
    user_a_email = make_email()
    resp_a = await async_client.post(
        "/api/v1/auth/register",
        json={"email": user_a_email, "password": "PasswordA123!", "full_name": "User Alpha"},
    )
    token_a = resp_a.json()["token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Register User B
    user_b_email = make_email()
    resp_b = await async_client.post(
        "/api/v1/auth/register",
        json={"email": user_b_email, "password": "PasswordB123!", "full_name": "User Beta"},
    )
    token_b = resp_b.json()["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A updates profile
    update_resp = await async_client.put(
        "/api/v1/profile/me",
        headers=headers_a,
        json={
            "headline": "Lead Systems Architect",
            "bio": "Building scalable platforms",
            "location": "Boston, MA",
            "target_job_titles": ["Staff Engineer", "Solutions Architect"],
            "remote_preference": "remote",
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["headline"] == "Lead Systems Architect"

    # User A reads own profile
    profile_a = await async_client.get("/api/v1/profile/me", headers=headers_a)
    assert profile_a.status_code == 200
    assert profile_a.json()["full_name"] == "User Alpha"
    assert profile_a.json()["profile"]["headline"] == "Lead Systems Architect"

    # User B reads own profile and does NOT see User A's data
    profile_b = await async_client.get("/api/v1/profile/me", headers=headers_b)
    assert profile_b.status_code == 200
    assert profile_b.json()["full_name"] == "User Beta"
    assert profile_b.json()["profile"]["headline"] is None

    # User B adds a skill
    skill_resp = await async_client.post(
        "/api/v1/profile/skills",
        headers=headers_b,
        json={"name": "Rust", "category": "technical", "proficiency_level": "expert", "years_experience": 3.0},
    )
    assert skill_resp.status_code == 201
    skill_b_id = skill_resp.json()["id"]

    # User A attempts to DELETE User B's skill -> MUST be rejected with 403 Forbidden!
    del_forbidden = await async_client.delete(f"/api/v1/profile/skills/{skill_b_id}", headers=headers_a)
    assert del_forbidden.status_code == 403
    assert "Access denied" in del_forbidden.json()["detail"]

    # User A attempts to delete non-existent skill -> 404
    del_notfound = await async_client.delete("/api/v1/profile/skills/999999", headers=headers_a)
    assert del_notfound.status_code == 404

    # User B deletes own skill -> 200 OK
    del_success = await async_client.delete(f"/api/v1/profile/skills/{skill_b_id}", headers=headers_b)
    assert del_success.status_code == 200


@pytest.mark.asyncio
async def test_education_experience_project_ownership(async_client: AsyncClient) -> None:
    """Validate ownership checks on Education, Experience, and Projects."""
    # Register User A and User B
    resp_a = await async_client.post(
        "/api/v1/auth/register",
        json={"email": make_email(), "password": "PasswordA123!", "full_name": "User A"},
    )
    headers_a = {"Authorization": f"Bearer {resp_a.json()['token']}"}

    resp_b = await async_client.post(
        "/api/v1/auth/register",
        json={"email": make_email(), "password": "PasswordB123!", "full_name": "User B"},
    )
    headers_b = {"Authorization": f"Bearer {resp_b.json()['token']}"}

    # User B creates Education, Experience, Project
    edu_resp = await async_client.post(
        "/api/v1/profile/education",
        headers=headers_b,
        json={"institution": "MIT", "degree": "M.S.", "field_of_study": "AI"},
    )
    assert edu_resp.status_code == 201
    edu_id = edu_resp.json()["id"]

    exp_resp = await async_client.post(
        "/api/v1/profile/experience",
        headers=headers_b,
        json={"company": "Acme AI", "title": "Senior AI Engineer"},
    )
    assert exp_resp.status_code == 201
    exp_id = exp_resp.json()["id"]

    proj_resp = await async_client.post(
        "/api/v1/profile/projects",
        headers=headers_b,
        json={"title": "Autonomous Agent", "technologies": ["Python", "FastAPI"]},
    )
    assert proj_resp.status_code == 201
    proj_id = proj_resp.json()["id"]

    # User A attempts to delete User B's resources -> 403 Forbidden on all
    assert (await async_client.delete(f"/api/v1/profile/education/{edu_id}", headers=headers_a)).status_code == 403
    assert (await async_client.delete(f"/api/v1/profile/experience/{exp_id}", headers=headers_a)).status_code == 403
    assert (await async_client.delete(f"/api/v1/profile/projects/{proj_id}", headers=headers_a)).status_code == 403

    # User B can delete own resources
    assert (await async_client.delete(f"/api/v1/profile/education/{edu_id}", headers=headers_b)).status_code == 200
    assert (await async_client.delete(f"/api/v1/profile/experience/{exp_id}", headers=headers_b)).status_code == 200
    assert (await async_client.delete(f"/api/v1/profile/projects/{proj_id}", headers=headers_b)).status_code == 200
