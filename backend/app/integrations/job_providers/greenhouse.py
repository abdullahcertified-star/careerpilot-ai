"""Greenhouse Job Board API provider adapter."""

import asyncio
from datetime import datetime, timezone
import logging
import re
from typing import Any, List, Optional
import httpx

from app.integrations.job_providers.base import JobProvider
from app.schemas.job import JobSearchQuery, JobSearchResult, NormalizedJob, ProviderCapabilities
from app.services.html_sanitizer import sanitize_html_content

logger = logging.getLogger(__name__)

DEFAULT_GREENHOUSE_BOARDS = ["gitlab", "cloudflare"]
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 3
RATE_LIMIT_CALLS_PER_MINUTE = 60


class GreenhouseAdapter(JobProvider):
    """
    Live adapter for public Greenhouse Job Boards.
    Interacts with https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs.
    Requires no secret API keys for publicly enabled customer job boards.
    """

    def __init__(
        self,
        default_boards: Optional[List[str]] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
    ):
        self.default_boards = default_boards or DEFAULT_GREENHOUSE_BOARDS
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._request_timestamps: List[float] = []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id="greenhouse",
            name="Greenhouse Job Board",
            description="Verified direct REST API for public job boards hosted on Greenhouse. Real-time listing and details retrieval.",
            integration_status="verified_live_api",
            supports_search=True,
            supports_details=True,
            supports_url_import=True,
            is_direct_api=True,
            link_first_only=False,
            rate_limit_rpm=RATE_LIMIT_CALLS_PER_MINUTE,
            documentation_url="https://developers.greenhouse.io/job-board.html",
        )

    async def _rate_limit_check(self) -> None:
        """Simple in-memory sliding-window rate limit regulator."""
        loop = asyncio.get_event_loop()
        now = loop.time()
        # Keep timestamps from the last 60 seconds
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 60.0]
        if len(self._request_timestamps) >= RATE_LIMIT_CALLS_PER_MINUTE:
            sleep_time = 60.0 - (now - self._request_timestamps[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        self._request_timestamps.append(loop.time())

    async def _http_get_with_retry(self, url: str) -> httpx.Response:
        """Bounded retries with exponential backoff for transient 429/5xx errors."""
        await self._rate_limit_check()
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(
                        url,
                        headers={"User-Agent": "CareerPilotAI/1.0 (+https://careerpilot.ai; JobDiscoveryEngine)"},
                    )

                    if response.status_code == 429 or 500 <= response.status_code < 600:
                        if attempt < self.max_retries:
                            backoff = 0.5 * (2 ** (attempt - 1))
                            await asyncio.sleep(backoff)
                            continue

                    return response
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)
                else:
                    break

        raise ConnectionError(
            f"Greenhouse API request to '{url}' failed after {self.max_retries} attempts: {last_error}"
        )

    def normalize(self, raw_data: Any, context: Optional[dict] = None) -> NormalizedJob:
        board_token = (context or {}).get("board_token", "greenhouse")
        job_id = str(raw_data.get("id", ""))
        title = raw_data.get("title", "Untitled Position")
        company = raw_data.get("company_name") or board_token.title()

        # Extract location
        loc_data = raw_data.get("location")
        location_str: Optional[str] = None
        if isinstance(loc_data, dict):
            location_str = loc_data.get("name")
        elif isinstance(loc_data, str):
            location_str = loc_data

        # Detect work mode
        work_mode = "unspecified"
        combined_text = f"{title} {location_str or ''}".lower()
        if "remote" in combined_text or "work from home" in combined_text:
            work_mode = "remote"
        elif "hybrid" in combined_text:
            work_mode = "hybrid"
        elif location_str:
            work_mode = "onsite"

        # Sanitize HTML content
        raw_content = raw_data.get("content", "")
        description = sanitize_html_content(raw_content) if raw_content else f"Open position for {title} at {company}."

        # Department
        departments = raw_data.get("departments", [])
        dept_name = departments[0].get("name") if departments and isinstance(departments[0], dict) else None

        # Posted timestamp
        posted_at: Optional[datetime] = None
        updated_str = raw_data.get("updated_at") or raw_data.get("first_published")
        if updated_str:
            try:
                # Greenhouse returns ISO timestamps e.g. 2026-03-24T10:14:13-04:00
                posted_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            except Exception:
                posted_at = None

        canonical_url = raw_data.get("absolute_url") or f"https://job-boards.greenhouse.io/{board_token}/jobs/{job_id}"

        return NormalizedJob(
            source="greenhouse",
            source_id=job_id,
            canonical_url=canonical_url,
            title=title,
            company=company,
            description=description,
            location=location_str,
            work_mode=work_mode,
            employment_type="full_time",
            department=dept_name,
            posted_at=posted_at,
            retrieved_at=datetime.now(timezone.utc),
            raw_metadata={
                "board_token": board_token,
                "internal_job_id": raw_data.get("internal_job_id"),
                "requisition_id": raw_data.get("requisition_id"),
            },
        )

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        boards_to_query = [query.board_token] if query.board_token else self.default_boards
        all_jobs: List[NormalizedJob] = []
        warnings: List[str] = []

        for board in boards_to_query:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            try:
                response = await self._http_get_with_retry(url)
                if response.status_code == 200:
                    payload = response.json()
                    jobs_list = payload.get("jobs", [])
                    for raw_job in jobs_list:
                        normalized = self.normalize(raw_job, context={"board_token": board})
                        all_jobs.append(normalized)
                elif response.status_code == 404:
                    warnings.append(f"Greenhouse board '{board}' was not found (404).")
                else:
                    warnings.append(f"Greenhouse board '{board}' returned HTTP {response.status_code}.")
            except Exception as exc:
                warnings.append(f"Failed to query Greenhouse board '{board}': {str(exc)}")

        # Client-side filtering across keywords, location, work_mode
        filtered_jobs = all_jobs

        if query.query:
            kw = query.query.strip().lower()
            filtered_jobs = [
                j for j in filtered_jobs
                if kw in j.title.lower() or (j.department and kw in j.department.lower()) or kw in j.description.lower()
            ]

        if query.location:
            loc_filter = query.location.strip().lower()
            filtered_jobs = [
                j for j in filtered_jobs
                if j.location and loc_filter in j.location.lower()
            ]

        if query.work_mode and query.work_mode != "all":
            wm_filter = query.work_mode.strip().lower()
            filtered_jobs = [
                j for j in filtered_jobs
                if j.work_mode.lower() == wm_filter
            ]

        total_count = len(filtered_jobs)
        start_idx = (query.page - 1) * query.page_size
        end_idx = start_idx + query.page_size
        paginated_jobs = filtered_jobs[start_idx:end_idx]

        return JobSearchResult(
            jobs=paginated_jobs,
            total_count=total_count,
            page=query.page,
            page_size=query.page_size,
            has_more=end_idx < total_count,
            provider_id="greenhouse",
            provider_status="verified_live_api",
            warnings=warnings,
        )

    async def fetch_details(
        self, job_id: str, board_token: Optional[str] = None
    ) -> Optional[NormalizedJob]:
        board = board_token or self.default_boards[0]
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"

        try:
            response = await self._http_get_with_retry(url)
            if response.status_code == 200:
                raw_data = response.json()
                return self.normalize(raw_data, context={"board_token": board})
            return None
        except Exception as exc:
            logger.warning("Error fetching Greenhouse job %s: %s", job_id, exc)
            return None
