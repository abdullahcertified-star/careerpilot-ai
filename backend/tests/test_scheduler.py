"""Comprehensive tests for Phase 8: Scheduled job discovery and notifications.

Preconditions & Verification Requirements:
1. Scheduled jobs execute at the configured times (interval calculation and due search retrieval).
2. Duplicate scans do not create duplicate listings (idempotent ingestion via canonical_url / source_id).
3. Retries respect the configured maximum (max retries with backoff and jitter).
4. Provider rate limits are respected (sliding window enforcement).
5. Paused and deleted searches do not continue scheduling.
6. Worker restarts recover or safely reschedule pending/stalled work.
7. Notifications are associated with the correct user (isolation across candidates).
8. Scheduled scans never submit applications (application and submission counts remain 0).
9. Missing Redis or provider availability produces a visible error rather than silent data loss.
10. Cancel long-running scans and inspect failures.
11. Email notifications require explicit consent and configured credentials.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import generate_session_token
from app.integrations.job_providers.base import JobProvider
from app.integrations.job_providers.registry import registry
from app.models.entities import (
    ApplicationSubmissionAttempt,
    JobApplication,
    JobPosting,
    Notification,
    Profile,
    SavedSearch,
    ScheduledScanRun,
    Skill,
    User,
    UserSession,
)
from app.schemas.job import (
    JobSearchQuery,
    JobSearchResult,
    NormalizedJob,
    ProviderCapabilities,
)
from app.services.scheduler.notification_service import notification_service
from app.services.scheduler.rate_limiter import (
    ProviderRateLimiter,
    ProviderRateLimitExceededError,
)
from app.services.scheduler.redis_client import (
    RedisUnavailableError,
    reset_redis_client_for_testing,
    set_redis_client_for_testing,
)
from app.services.scheduler.scanner import ScheduledJobScanner
from app.services.scheduler.worker import ScheduledScanWorker


class MockScheduledProviderAdapter(JobProvider):
    """Mock job board adapter for deterministic scheduled scanner testing."""

    def __init__(self, provider_id: str = "greenhouse", listings: list[NormalizedJob] | None = None):
        self._provider_id = provider_id
        self._listings = listings or []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self._provider_id,
            name="Mock Provider Board",
            description="Mock board for scheduler testing",
            integration_status="verified_live_api",
            supports_search=True,
            supports_details=True,
            is_direct_api=True,
        )

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        return JobSearchResult(
            jobs=self._listings,
            total_count=len(self._listings),
            page=query.page,
            page_size=query.page_size,
            has_more=False,
            provider_id=self._provider_id,
            provider_status="ok",
        )

    async def fetch_details(self, job_id: str, board_token: str | None = None) -> NormalizedJob | None:
        for item in self._listings:
            if item.source_id == job_id:
                return item
        return None

    def normalize(self, raw_data: Any, context: dict | None = None) -> NormalizedJob:
        return raw_data


@pytest.fixture
def fake_redis():
    """Isolated in-memory async Redis instance for tests."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    set_redis_client_for_testing(client)
    yield client
    reset_redis_client_for_testing()


@pytest.fixture
async def candidate_alice():
    """Create test candidate Alice with profile and python skills."""
    uid = uuid.uuid4().hex[:8]
    email = f"alice_{uid}@example.com"
    async with async_session_factory() as session:
        user = User(
            email=email,
            hashed_password="hashed_pw_alice",
            full_name=f"Alice Engineer {uid}",
            role="job_seeker",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

        profile = Profile(
            user_id=user.id,
            headline="Senior Backend Engineer",
            bio="10+ years specializing in Python, FastAPI, and Distributed Systems",
            location="Remote",
            target_job_titles=["Senior Backend Engineer", "Lead Python Developer"],
            remote_preference="remote",
        )
        session.add(profile)

        for skill_name in ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"]:
            session.add(
                Skill(
                    user_id=user.id,
                    name=skill_name,
                    category="technical",
                    proficiency_level="expert",
                    years_experience=7,
                )
            )

        token, token_hash = generate_session_token()
        session_rec = UserSession(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            is_revoked=False,
        )
        session.add(session_rec)
        await session.commit()
        await session.refresh(user)
        user._test_token = token
        return user


@pytest.fixture
async def candidate_bob():
    """Create second test candidate Bob to verify user isolation."""
    uid = uuid.uuid4().hex[:8]
    email = f"bob_{uid}@example.com"
    async with async_session_factory() as session:
        user = User(
            email=email,
            hashed_password="hashed_pw_bob",
            full_name=f"Bob Frontend {uid}",
            role="job_seeker",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

        profile = Profile(
            user_id=user.id,
            headline="Frontend React Engineer",
            bio="Building modern accessible web interfaces.",
            location="New York",
            target_job_titles=["Frontend Developer"],
            remote_preference="hybrid",
        )
        session.add(profile)

        token, token_hash = generate_session_token()
        session_rec = UserSession(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            is_revoked=False,
        )
        session.add(session_rec)
        await session.commit()
        await session.refresh(user)
        user._test_token = token
        return user


@pytest.fixture
def alice_auth_headers(candidate_alice: User):
    return {"Authorization": f"Bearer {candidate_alice._test_token}"}


@pytest.fixture
def bob_auth_headers(candidate_bob: User):
    return {"Authorization": f"Bearer {candidate_bob._test_token}"}


# -------------------------------------------------------------------------
# Test 1: Scheduled jobs execute at configured times
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduled_jobs_execute_at_configured_times(fake_redis, candidate_alice: User):
    """Verify saved search computes next_run_at according to interval, worker identifies due searches, and advances next run time."""
    worker = ScheduledScanWorker(redis_client=fake_redis)

    async with async_session_factory() as session:
        search = SavedSearch(
            user_id=candidate_alice.id,
            name="Alice Python Alert",
            role="Backend Engineer",
            keywords=["Python"],
            location="Remote",
            interval_minutes=45,
            is_active=True,
            is_paused=False,
            next_run_at=datetime.now(UTC) - timedelta(minutes=5),  # already due
        )
        session.add(search)
        await session.commit()
        await session.refresh(search)
        search_id = search.id

    # 1. Worker retrieves due searches
    due_searches = await worker.get_due_saved_searches()
    due_ids = [s.id for s in due_searches]
    assert search_id in due_ids

    # 2. Worker executes scan
    run = await worker.execute_scan(search_id)
    assert run.status == "completed"
    assert run.saved_search_id == search_id
    assert run.duration_ms is not None
    assert run.duration_ms >= 0

    # 3. Verify next_run_at advanced by ~45 minutes
    async with async_session_factory() as session:
        updated = await session.get(SavedSearch, search_id)
        assert updated is not None
        assert updated.last_run_at is not None
        assert updated.last_success_at is not None
        assert updated.total_runs == 1
        assert updated.next_run_at is not None
        expected_min = datetime.now(UTC) + timedelta(minutes=40)
        expected_max = datetime.now(UTC) + timedelta(minutes=50)
        next_run = updated.next_run_at
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=UTC)
        assert expected_min <= next_run <= expected_max


# -------------------------------------------------------------------------
# Test 2: Idempotent Ingestion and Deduplication of Repeated Listings
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idempotent_ingestion_and_deduplication(fake_redis, candidate_alice: User):
    """Ensure duplicate job scans do not create duplicate JobPosting records."""
    unique_ext_id = f"job-{uuid.uuid4().hex[:6]}"
    canonical_url = f"https://example.com/jobs/{unique_ext_id}"

    sample_listing = NormalizedJob(
        source="greenhouse",
        source_id=unique_ext_id,
        canonical_url=canonical_url,
        title="Senior Python Backend Architect",
        company="TechCorp Global",
        description="Looking for an exceptional Python, FastAPI, and Redis specialist with 5+ years of experience.",
        location="Remote",
        work_mode="remote",
        employment_type="full_time",
        retrieved_at=datetime.now(UTC),
    )

    mock_adapter = MockScheduledProviderAdapter(provider_id="greenhouse", listings=[sample_listing])
    registry.register(mock_adapter)

    scanner = ScheduledJobScanner(redis_client=fake_redis)
    worker = ScheduledScanWorker(redis_client=fake_redis, scanner=scanner)

    async with async_session_factory() as session:
        search = SavedSearch(
            user_id=candidate_alice.id,
            name="Deduplication Verification Search",
            role="Python Backend",
            keywords=["Python"],
            location="Remote",
            interval_minutes=60,
            provider_id="greenhouse",
            is_active=True,
            is_paused=False,
        )
        session.add(search)
        await session.commit()
        await session.refresh(search)
        search_id = search.id

    # First Scan: Job is newly ingested
    run_1 = await worker.execute_scan(search_id)
    assert run_1.status == "completed"
    assert run_1.jobs_found >= 1
    assert run_1.new_jobs_ingested >= 1

    # Check database postings count
    async with async_session_factory() as session:
        postings = (
            (await session.execute(select(JobPosting).where(JobPosting.canonical_url == canonical_url)))
            .scalars()
            .all()
        )
        assert len(postings) == 1
        initial_id = postings[0].id

    # Second Scan: Re-scan with identical listing
    run_2 = await worker.execute_scan(search_id)
    assert run_2.status == "completed"
    assert run_2.jobs_found >= 1
    assert run_2.new_jobs_ingested == 0  # Deduplicated!

    # Check database postings count remains exactly 1
    async with async_session_factory() as session:
        postings = (
            (await session.execute(select(JobPosting).where(JobPosting.canonical_url == canonical_url)))
            .scalars()
            .all()
        )
        assert len(postings) == 1
        assert postings[0].id == initial_id  # Same record updated, no duplicate created


# -------------------------------------------------------------------------
# Test 3: Retries Respect Configured Maximum with Backoff and Jitter
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retries_respect_configured_maximum(fake_redis, candidate_alice: User):
    """Verify worker retries failing scans up to max_retries before marking run failed."""
    mock_failing_scanner = MagicMock(spec=ScheduledJobScanner)
    call_count = 0

    async def fail_scan(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("External network timeout connecting to provider")

    mock_failing_scanner.execute_scan = AsyncMock(side_effect=fail_scan)

    worker = ScheduledScanWorker(
        redis_client=fake_redis,
        scanner=mock_failing_scanner,
        max_retries=3,
        base_backoff_seconds=0.01,  # Speed up tests
    )

    async with async_session_factory() as session:
        search = SavedSearch(
            user_id=candidate_alice.id,
            name="Retry Test Search",
            role="Engineer",
            interval_minutes=60,
            is_active=True,
            is_paused=False,
        )
        session.add(search)
        await session.commit()
        await session.refresh(search)
        search_id = search.id

    run = await worker.execute_scan(search_id)

    # Total attempts = 1 initial + 3 retries = 4
    assert call_count == 4
    assert run.status == "failed"
    assert run.retry_count == 3
    assert "External network timeout" in (run.error_message or "")

    # Saved search tracks failure
    async with async_session_factory() as session:
        updated = await session.get(SavedSearch, search_id)
        assert updated is not None
        assert updated.consecutive_failures == 1
        assert updated.last_failure_at is not None
        assert "External network timeout" in (updated.last_error or "")


# -------------------------------------------------------------------------
# Test 4: Provider Rate Limits are Respected
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_provider_rate_limits_are_respected(fake_redis):
    """Verify sliding window rate limiter throttles calls once RPM is exceeded."""
    limiter = ProviderRateLimiter(fake_redis)
    test_provider = f"rate_limited_provider_{uuid.uuid4().hex[:6]}"

    # Set rate limit of 3 RPM
    limiter.set_provider_limit(test_provider, rpm=3)

    # Requests 1, 2, 3 should succeed
    for _ in range(3):
        res = await limiter.acquire(test_provider)
        assert res.acquired is True
        assert res.current_requests <= 3

    # Request 4 in same window should fail
    res_4 = await limiter.acquire(test_provider)
    assert res_4.acquired is False
    assert res_4.retry_after_seconds > 0

    # Strict check should raise ProviderRateLimitExceededError
    with pytest.raises(ProviderRateLimitExceededError) as exc_info:
        await limiter.check_and_acquire_strict(test_provider)
    assert exc_info.value.provider_id == test_provider
    assert exc_info.value.retry_after_seconds > 0


# -------------------------------------------------------------------------
# Test 5: Paused and Deleted Searches Do Not Continue Scheduling
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paused_and_deleted_searches_do_not_continue_scheduling(
    async_client: AsyncClient,
    alice_auth_headers: dict[str, str],
    fake_redis,
    candidate_alice: User,
):
    """Verify pausing or deleting a search halts scheduling."""
    create_payload = {
        "name": "Frontend Hybrid Role",
        "role": "Frontend Engineer",
        "keywords": ["React", "TypeScript"],
        "location": "New York",
        "interval_minutes": 30,
    }
    create_res = await async_client.post("/api/v1/saved-searches", json=create_payload, headers=alice_auth_headers)
    assert create_res.status_code == 201
    search_data = create_res.json()
    search_id = search_data["id"]

    worker = ScheduledScanWorker(redis_client=fake_redis)

    # Pause search via API
    pause_res = await async_client.post(f"/api/v1/saved-searches/{search_id}/pause", headers=alice_auth_headers)
    assert pause_res.status_code == 200
    assert pause_res.json()["is_paused"] is True

    # Artificially set next_run_at to past to see if worker would pick it up
    async with async_session_factory() as session:
        search = await session.get(SavedSearch, search_id)
        search.next_run_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    due_searches = await worker.get_due_saved_searches()
    due_ids = [s.id for s in due_searches]
    assert search_id not in due_ids  # Paused search MUST NOT be scheduled

    # Resume search
    resume_res = await async_client.post(f"/api/v1/saved-searches/{search_id}/resume", headers=alice_auth_headers)
    assert resume_res.status_code == 200
    assert resume_res.json()["is_paused"] is False

    # Now it should be due
    due_searches_resumed = await worker.get_due_saved_searches()
    assert search_id in [s.id for s in due_searches_resumed]

    # Delete search
    del_res = await async_client.delete(f"/api/v1/saved-searches/{search_id}", headers=alice_auth_headers)
    assert del_res.status_code in (200, 204)

    # Once deleted, it must not be scheduled
    due_searches_deleted = await worker.get_due_saved_searches()
    assert search_id not in [s.id for s in due_searches_deleted]


# -------------------------------------------------------------------------
# Test 6: Worker Restarts Recover or Safely Reschedule Pending Work
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_restarts_recover_stalled_scans(fake_redis, candidate_alice: User):
    """Simulate worker crash leaving a scan in 'running' state and verify recovery."""
    worker = ScheduledScanWorker(redis_client=fake_redis)

    async with async_session_factory() as session:
        search = SavedSearch(
            user_id=candidate_alice.id,
            name="Crash Recovery Search",
            interval_minutes=60,
            is_active=True,
            is_paused=False,
        )
        session.add(search)
        await session.flush()

        stalled_run = ScheduledScanRun(
            saved_search_id=search.id,
            idempotency_key=f"stalled-{uuid.uuid4().hex[:6]}",
            status="running",
            started_at=datetime.now(UTC) - timedelta(minutes=15),
        )
        session.add(stalled_run)
        await session.commit()
        await session.refresh(stalled_run)
        run_id = stalled_run.id
        search_id = search.id

    # Place a lingering lock in Redis to simulate crash during lock acquisition
    lock_key = f"scan:lock:{search_id}"
    await fake_redis.set(lock_key, "stalled-worker-id", ex=300)
    assert await fake_redis.exists(lock_key) == 1

    # Run restart recovery
    recovered_count = await worker.recover_pending_or_stalled_scans(stale_threshold_seconds=60)
    assert recovered_count >= 1

    # Verify run status is recovered and lock is released
    async with async_session_factory() as session:
        run_record = await session.get(ScheduledScanRun, run_id)
        assert run_record is not None
        assert run_record.status == "failed"
        assert "worker restart" in (run_record.error_message or "")

    assert await fake_redis.exists(lock_key) == 0  # Stale lock cleaned up!


# -------------------------------------------------------------------------
# Test 7: Notifications are Associated with the Correct User
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notifications_associated_with_correct_user(
    async_client: AsyncClient,
    alice_auth_headers: dict[str, str],
    bob_auth_headers: dict[str, str],
    candidate_alice: User,
    candidate_bob: User,
):
    """Ensure in-app notifications are strictly scoped to the receiving candidate."""
    async with async_session_factory() as session:
        notif_alice = Notification(
            user_id=candidate_alice.id,
            type="high_match_job",
            title="Alice Notification",
            message="Top matching Python job found for Alice",
            data={"match_score": 95.0},
            is_read=False,
        )
        notif_bob = Notification(
            user_id=candidate_bob.id,
            type="high_match_job",
            title="Bob Notification",
            message="Top matching React job found for Bob",
            data={"match_score": 88.0},
            is_read=False,
        )
        session.add_all([notif_alice, notif_bob])
        await session.commit()
        await session.refresh(notif_alice)
        await session.refresh(notif_bob)
        alice_notif_id = notif_alice.id
        bob_notif_id = notif_bob.id

    # Alice queries notifications
    alice_res = await async_client.get("/api/v1/notifications", headers=alice_auth_headers)
    assert alice_res.status_code == 200
    alice_items = alice_res.json()["items"]
    alice_ids = [item["id"] for item in alice_items]
    assert alice_notif_id in alice_ids
    assert bob_notif_id not in alice_ids  # Bob's notification is invisible to Alice

    # Alice unread count
    count_res = await async_client.get("/api/v1/notifications/unread-count", headers=alice_auth_headers)
    assert count_res.status_code == 200
    assert count_res.json()["unread_count"] >= 1

    # Bob tries to mark Alice's notification as read (Not Found / Forbidden)
    tamper_res = await async_client.patch(f"/api/v1/notifications/{alice_notif_id}/read", headers=bob_auth_headers)
    assert tamper_res.status_code == 404

    # Alice marks her own notification as read
    read_res = await async_client.patch(f"/api/v1/notifications/{alice_notif_id}/read", headers=alice_auth_headers)
    assert read_res.status_code == 200
    assert read_res.json()["is_read"] is True

    # Mark all read for Alice
    mark_all = await async_client.post("/api/v1/notifications/read-all", headers=alice_auth_headers)
    assert mark_all.status_code == 200


# -------------------------------------------------------------------------
# Test 8: Scheduled Scans Never Submit Applications
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduled_scans_never_submit_applications(fake_redis, candidate_alice: User):
    """CRITICAL: Scheduled discovery scans must NEVER submit applications or create submission attempts."""
    high_match_listing = NormalizedJob(
        source="greenhouse",
        source_id=f"auto-scan-{uuid.uuid4().hex[:6]}",
        canonical_url=f"https://example.com/jobs/staff-{uuid.uuid4().hex[:6]}",
        title="Senior Python Backend Engineer",
        company="Autonomous Safety Org",
        description="Senior Python developer with FastAPI, PostgreSQL, Redis, and distributed systems experience.",
        location="Remote",
        work_mode="remote",
        employment_type="full_time",
        retrieved_at=datetime.now(UTC),
    )

    mock_adapter = MockScheduledProviderAdapter(provider_id="greenhouse", listings=[high_match_listing])
    registry.register(mock_adapter)

    scanner = ScheduledJobScanner(redis_client=fake_redis)
    worker = ScheduledScanWorker(redis_client=fake_redis, scanner=scanner)

    async with async_session_factory() as session:
        initial_apps_count = (
            await session.execute(select(JobApplication).where(JobApplication.user_id == candidate_alice.id))
        ).scalars().all()
        initial_attempts_count = (
            await session.execute(
                select(ApplicationSubmissionAttempt).where(ApplicationSubmissionAttempt.actor_id == str(candidate_alice.id))
            )
        ).scalars().all()

        search = SavedSearch(
            user_id=candidate_alice.id,
            name="No-Auto-Submit Security Test",
            role="Senior Python Engineer",
            keywords=["Python", "FastAPI"],
            location="Remote",
            interval_minutes=30,
            min_match_score=60.0,
            provider_id="greenhouse",
            is_active=True,
            is_paused=False,
        )
        session.add(search)
        await session.commit()
        await session.refresh(search)
        search_id = search.id

    # Execute discovery scan
    run = await worker.execute_scan(search_id)
    assert run.status == "completed"
    assert run.jobs_found >= 1

    # Verify database state after scan
    async with async_session_factory() as session:
        submitted_apps = (
            await session.execute(
                select(JobApplication)
                .where(JobApplication.user_id == candidate_alice.id)
                .where(JobApplication.status == "submitted")
            )
        ).scalars().all()
        all_apps = (
            await session.execute(select(JobApplication).where(JobApplication.user_id == candidate_alice.id))
        ).scalars().all()
        assert len(all_apps) == len(initial_apps_count)
        assert len(submitted_apps) == 0

        # Application submission attempts must remain 0
        attempts = (
            await session.execute(
                select(ApplicationSubmissionAttempt).where(
                    ApplicationSubmissionAttempt.actor_id == str(candidate_alice.id)
                )
            )
        ).scalars().all()
        assert len(attempts) == len(initial_attempts_count)

        # High match notification was created for Alice, but NO automatic application submission occurred
        notifs = (
            await session.execute(
                select(Notification)
                .where(Notification.user_id == candidate_alice.id)
                .where(Notification.type == "high_match_job")
            )
        ).scalars().all()
        assert len(notifs) >= 1


# -------------------------------------------------------------------------
# Test 9: Missing Redis or Provider Availability Produces Visible Error
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_redis_produces_visible_error(
    async_client: AsyncClient,
    alice_auth_headers: dict[str, str],
    candidate_alice: User,
):
    """Verify that unavailable Redis raises a visible error (HTTP 503) rather than silent failure."""
    reset_redis_client_for_testing()

    with patch(
        "app.services.scheduler.service.check_redis_availability",
        side_effect=RedisUnavailableError("Redis connection refused on localhost:6379"),
    ):
        async with async_session_factory() as session:
            search = SavedSearch(
                user_id=candidate_alice.id,
                name="Redis Unavailable Check",
                interval_minutes=60,
                is_active=True,
            )
            session.add(search)
            await session.commit()
            await session.refresh(search)
            search_id = search.id

        # Calling run-now when Redis is down must return HTTP 503 with visible error message
        res = await async_client.post(f"/api/v1/saved-searches/{search_id}/run-now", headers=alice_auth_headers)
        assert res.status_code == 503
        error_detail = res.json()["detail"].lower()
        assert "redis" in error_detail
        assert "unreachable" in error_detail or "refused" in error_detail


# -------------------------------------------------------------------------
# Test 10: Cancel Long-Running Scans and Inspect Failures
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_scan_and_inspect_run_status(
    async_client: AsyncClient,
    alice_auth_headers: dict[str, str],
    fake_redis,
    candidate_alice: User,
):
    """Verify scan cancellation requests set Redis flag and scanner terminates execution."""
    scanner = ScheduledJobScanner(redis_client=fake_redis)
    worker = ScheduledScanWorker(redis_client=fake_redis, scanner=scanner)

    async with async_session_factory() as session:
        search = SavedSearch(
            user_id=candidate_alice.id,
            name="Cancellable Long Running Search",
            interval_minutes=60,
            is_active=True,
            is_paused=False,
        )
        session.add(search)
        await session.commit()
        await session.refresh(search)
        search_id = search.id

    # Pre-set cancellation flag in Redis
    await worker.request_scan_cancellation(search_id)

    # Execute scan - should detect cancellation immediately
    run = await worker.execute_scan(search_id)
    assert run.status == "cancelled"
    assert "Scan cancelled" in (run.error_message or "")

    # Inspect runs via API
    runs_res = await async_client.get(f"/api/v1/saved-searches/{search_id}/runs", headers=alice_auth_headers)
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 1
    assert runs[0]["status"] == "cancelled"
    assert "Scan cancelled" in (runs[0]["error_message"] or "")


# -------------------------------------------------------------------------
# Test 11: Email Notifications Require Consent and Configured Credentials
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_email_notifications_require_credentials_and_consent(candidate_alice: User):
    """Ensure email notifications are withheld unless user has given consent and credentials exist."""
    # 1. No consent -> withheld
    dispatched_no_consent = await notification_service.dispatch_email_if_permitted(
        user=candidate_alice,
        subject="New Match",
        body_text="A high match job was found.",
        user_consented=False,
    )
    assert dispatched_no_consent is False

    # 2. Consented, but mock missing SMTP settings
    with patch("app.services.scheduler.notification_service.settings") as mock_settings:
        mock_settings.SMTP_HOST = ""
        mock_settings.SMTP_USER = ""
        mock_settings.SMTP_PASSWORD = ""
        dispatched_missing_creds = await notification_service.dispatch_email_if_permitted(
            user=candidate_alice,
            subject="New Match",
            body_text="A high match job was found.",
            user_consented=True,
        )
        assert dispatched_missing_creds is False

    # 3. Consented and configured credentials -> dispatches successfully
    with patch("app.services.scheduler.notification_service.settings") as mock_settings:
        mock_settings.SMTP_HOST = "smtp.example.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USER = "test-user@example.com"
        mock_settings.SMTP_PASSWORD = "mock-test-auth-token"
        mock_settings.EMAILS_FROM_EMAIL = "alerts@example.com"

        dispatched_ready = await notification_service.dispatch_email_if_permitted(
            user=candidate_alice,
            subject="New Match",
            body_text="A high match job was found.",
            user_consented=True,
        )
        assert dispatched_ready is True
