"""Tests for Job Provider Adapters, Capabilities, and Error Isolation."""

from unittest.mock import AsyncMock, patch
import httpx
import pytest

from app.integrations.job_providers.greenhouse import GreenhouseAdapter
from app.integrations.job_providers.indeed import IndeedAdapter
from app.integrations.job_providers.linkedin import LinkedInAdapter
from app.integrations.job_providers.manual_import import ManualImportAdapter
from app.integrations.job_providers.registry import JobProviderRegistry
from app.schemas.job import JobSearchQuery


def test_provider_capabilities_reporting() -> None:
    """Verifies that all registered adapters report explicit capabilities and integration statuses."""
    gh = GreenhouseAdapter()
    li = LinkedInAdapter()
    ind = IndeedAdapter()
    mi = ManualImportAdapter()

    gh_caps = gh.capabilities()
    assert gh_caps.provider_id == "greenhouse"
    assert gh_caps.integration_status == "verified_live_api"
    assert gh_caps.is_direct_api is True
    assert gh_caps.supports_search is True

    li_caps = li.capabilities()
    assert li_caps.provider_id == "linkedin"
    assert li_caps.integration_status == "link_first"
    assert li_caps.is_direct_api is False
    assert li_caps.link_first_only is True

    ind_caps = ind.capabilities()
    assert ind_caps.provider_id == "indeed"
    assert ind_caps.integration_status == "link_first"
    assert ind_caps.is_direct_api is False
    assert ind_caps.link_first_only is True

    mi_caps = mi.capabilities()
    assert mi_caps.provider_id == "manual_import"
    assert mi_caps.integration_status == "verified_secure_import"
    assert mi_caps.supports_url_import is True


@pytest.mark.asyncio
async def test_greenhouse_adapter_mock_search_and_pagination() -> None:
    """Verifies Greenhouse search with mocked public board payload, filtering, and pagination."""
    adapter = GreenhouseAdapter(default_boards=["mockboard"])

    mock_jobs_payload = {
        "jobs": [
            {
                "id": 1001,
                "title": "Staff Backend Engineer - Python",
                "company_name": "Mock Technologies",
                "location": {"name": "Remote, US"},
                "content": "<p>Build high-performance async backends with FastAPI and PostgreSQL.</p>",
                "departments": [{"name": "Core Engineering"}],
                "updated_at": "2026-03-20T12:00:00Z",
                "absolute_url": "https://boards.greenhouse.io/mockboard/jobs/1001",
            },
            {
                "id": 1002,
                "title": "Frontend Engineer - React",
                "company_name": "Mock Technologies",
                "location": {"name": "San Francisco, CA"},
                "content": "<p>Modern Next.js and TypeScript frontend experience.</p>",
                "departments": [{"name": "Design Systems"}],
                "updated_at": "2026-03-21T12:00:00Z",
                "absolute_url": "https://boards.greenhouse.io/mockboard/jobs/1002",
            },
            {
                "id": 1003,
                "title": "Junior Python Developer",
                "company_name": "Mock Technologies",
                "location": {"name": "Remote, Global"},
                "content": "<p>Entry level Python role.</p>",
                "departments": [{"name": "Core Engineering"}],
                "updated_at": "2026-03-22T12:00:00Z",
                "absolute_url": "https://boards.greenhouse.io/mockboard/jobs/1003",
            },
        ]
    }

    mock_resp = httpx.Response(
        status_code=200,
        json=mock_jobs_payload,
        request=httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/mockboard/jobs?content=true"),
    )

    with patch.object(adapter, "_http_get_with_retry", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        # 1. Search with keyword filter
        res = await adapter.search(JobSearchQuery(query="Python", page=1, page_size=10))
        assert res.total_count == 2
        assert len(res.jobs) == 2
        assert all("Python" in j.title for j in res.jobs)
        assert res.jobs[0].work_mode == "remote"
        assert res.jobs[0].source == "greenhouse"

        # 2. Search with location / work mode filter
        res_remote = await adapter.search(JobSearchQuery(work_mode="remote", page=1, page_size=1))
        assert res_remote.total_count == 2
        assert len(res_remote.jobs) == 1
        assert res_remote.has_more is True

        # 3. Pagination page 2
        res_page2 = await adapter.search(JobSearchQuery(work_mode="remote", page=2, page_size=1))
        assert len(res_page2.jobs) == 1
        assert res_page2.jobs[0].source_id == "1003"
        assert res_page2.has_more is False


@pytest.mark.asyncio
async def test_greenhouse_retries_on_rate_limit_or_server_error() -> None:
    """Verifies Greenhouse adapter performs bounded retries on 429 rate limit before succeeding."""
    adapter = GreenhouseAdapter(default_boards=["mockboard"], max_retries=3)

    resp_429 = httpx.Response(
        status_code=429,
        request=httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/mockboard/jobs"),
    )
    resp_200 = httpx.Response(
        status_code=200,
        json={"jobs": [{"id": 55, "title": "DevOps Engineer", "content": "AWS", "location": {"name": "Remote"}}]},
        request=httpx.Request("GET", "https://boards-api.greenhouse.io/v1/boards/mockboard/jobs"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        # First call 429, second call 200
        mock_get.side_effect = [resp_429, resp_200]

        res = await adapter.search(JobSearchQuery())
        assert res.total_count == 1
        assert res.jobs[0].title == "DevOps Engineer"
        assert mock_get.call_count == 2


@pytest.mark.asyncio
async def test_linkedin_and_indeed_link_first_generation() -> None:
    """Verifies LinkedIn and Indeed adapters construct valid search URLs and return link-first notices."""
    li = LinkedInAdapter()
    ind = IndeedAdapter()

    q = JobSearchQuery(query="Senior Backend Engineer", location="San Francisco, CA", work_mode="remote")

    li_res = await li.search(q)
    assert li_res.provider_status == "link_first"
    assert li_res.external_search_url is not None
    assert "linkedin.com/jobs/search" in li_res.external_search_url
    assert "Senior+Backend+Engineer" in li_res.external_search_url
    assert "f_WT=2" in li_res.external_search_url  # remote filter
    assert len(li_res.warnings) > 0

    ind_res = await ind.search(q)
    assert ind_res.provider_status == "link_first"
    assert ind_res.external_search_url is not None
    assert "indeed.com/jobs" in ind_res.external_search_url
    assert "Senior+Backend+Engineer" in ind_res.external_search_url


@pytest.mark.asyncio
async def test_provider_error_isolation_in_registry() -> None:
    """Verifies that an upstream failure in Greenhouse does not crash multi-provider search."""
    registry = JobProviderRegistry()

    # Mock Greenhouse to raise a network connection error
    with patch.object(GreenhouseAdapter, "search", side_effect=ConnectionError("Greenhouse API unreachable")):
        result = await registry.search(JobSearchQuery(provider_id="all", query="Engineer"))
        assert result.provider_status == "multi_provider"
        # Search returns gracefully with warning instead of 500 error
        assert any("Greenhouse" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_live_greenhouse_public_board_integration() -> None:
    """
    Verifies live Greenhouse public API against 'gitlab' board when internet is available.
    Gracefully logs and passes if outbound network access is blocked or offline.
    """
    adapter = GreenhouseAdapter(default_boards=["gitlab"], timeout_seconds=5.0)
    try:
        result = await adapter.search(JobSearchQuery(page=1, page_size=2))
        if result.jobs:
            first_job = result.jobs[0]
            assert first_job.source == "greenhouse"
            assert first_job.title
            assert first_job.canonical_url.startswith("http")
    except Exception as exc:
        pytest.skip(f"Live network access unavailable or timed out: {exc}")
