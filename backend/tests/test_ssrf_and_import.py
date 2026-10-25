"""Tests for SSRF prevention, safe URL fetching, and HTML job extraction."""

import ipaddress
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from app.services.html_sanitizer import extract_job_from_html, sanitize_html_content
from app.services.ssrf_protector import (
    SSRFSecurityError,
    safe_fetch_url,
    validate_and_resolve_url,
)


def test_ssrf_blocks_invalid_schemes() -> None:
    """Verifies non-HTTP/HTTPS schemes are immediately rejected."""
    prohibited_schemes = [
        "file:///etc/passwd",
        "ftp://ftp.example.com/job.txt",
        "gopher://gopher.example.com",
        "javascript:alert(1)",
        "data:text/html,<h1>Job</h1>",
    ]
    for url in prohibited_schemes:
        with pytest.raises(SSRFSecurityError) as exc_info:
            validate_and_resolve_url(url)
        assert "scheme" in str(exc_info.value).lower() or "prohibited" in str(exc_info.value).lower()


def test_ssrf_blocks_loopback_and_private_ips() -> None:
    """Verifies loopback, private networks, and metadata IPs are rejected."""
    prohibited_urls = [
        "http://127.0.0.1:8000/internal",
        "http://127.0.0.2:9000",
        "http://localhost:8000",
        "http://10.0.0.1/admin",
        "http://172.16.0.1/metadata",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0:8000",
    ]
    for url in prohibited_urls:
        with pytest.raises(SSRFSecurityError) as exc_info:
            validate_and_resolve_url(url)
        assert "restricted" in str(exc_info.value).lower() or "prohibited" in str(exc_info.value).lower()


def test_ssrf_blocks_credentials_in_url() -> None:
    """Verifies user credentials in authority component are rejected."""
    with pytest.raises(SSRFSecurityError) as exc_info:
        validate_and_resolve_url("http://user:password@example.com/job")
    assert "credential" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_ssrf_blocks_redirect_chain_to_internal_ip() -> None:
    """Verifies safe_fetch_url detects and blocks redirects leading to private or loopback destinations."""
    # First response is a 302 redirecting to http://127.0.0.1/internal
    resp_redirect = httpx.Response(
        status_code=302,
        headers={"location": "http://127.0.0.1:8000/secret"},
        request=httpx.Request("GET", "https://example.com/job"),
    )

    with patch("app.services.ssrf_protector.validate_and_resolve_url") as mock_validate:
        # First call passes (example.com), second call checks redirect target and raises
        def side_effect(u: str):
            if "127.0.0.1" in u:
                raise SSRFSecurityError("Prohibited network destination: restricted IP '127.0.0.1'")
            return u, ["93.184.216.34"]

        mock_validate.side_effect = side_effect

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_redirect

            with pytest.raises(SSRFSecurityError) as exc_info:
                await safe_fetch_url("https://example.com/job")

            assert "restricted" in str(exc_info.value).lower() or "prohibited" in str(exc_info.value).lower()


def test_html_sanitizer_strips_scripts_and_events() -> None:
    """Verifies sanitize_html_content removes harmful executable tags and event handlers."""
    malicious_html = """
    <div>
        <h1>Senior Developer</h1>
        <script>alert("pwned");</script>
        <p onclick="stealCookies()">Great position with competitive salary.</p>
        <iframe src="http://evil.com"></iframe>
    </div>
    """
    clean_text = sanitize_html_content(malicious_html)
    assert "alert" not in clean_text
    assert "stealCookies" not in clean_text
    assert "evil.com" not in clean_text
    assert "Senior Developer" in clean_text
    assert "Great position with competitive salary." in clean_text


def test_html_extraction_with_json_ld() -> None:
    """Verifies extract_job_from_html parses Schema.org JobPosting structured metadata."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ignored title tag</title>
        <script type="application/ld+json">
        {
            "@type": "JobPosting",
            "title": "Principal Distributed Systems Engineer",
            "description": "<p>We are seeking a senior engineer to scale our cluster architecture.</p>",
            "hiringOrganization": {
                "@type": "Organization",
                "name": "Acme Cloud Corp"
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "addressLocality": "Austin",
                    "addressRegion": "TX",
                    "addressCountry": "USA"
                }
            },
            "jobLocationType": "TELECOMMUTE",
            "employmentType": "FULL_TIME"
        }
        </script>
        <link rel="canonical" href="https://acme.com/jobs/principal-distributed-systems" />
    </head>
    <body>
        <h1>Fallbacks not used</h1>
    </body>
    </html>
    """
    data = extract_job_from_html(html, base_url="https://acme.com/jobs/ref123")
    assert data["title"] == "Principal Distributed Systems Engineer"
    assert data["company"] == "Acme Cloud Corp"
    assert "scale our cluster architecture" in data["description"]
    assert "Austin" in data["location"]
    assert data["work_mode"] == "remote"
    assert data["employment_type"] == "full_time"
    assert data["canonical_url"] == "https://acme.com/jobs/principal-distributed-systems"


def test_html_extraction_with_opengraph_fallback() -> None:
    """Verifies extract_job_from_html correctly extracts from OpenGraph meta tags."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="og:title" content="DevOps Lead at FinTech Innovations" />
        <meta property="og:site_name" content="FinTech Innovations" />
        <meta property="og:description" content="Manage multi-region AWS Kubernetes infrastructure." />
    </head>
    <body>
        <main>
            <p>Remote, United States. Competitive compensation package.</p>
        </main>
    </body>
    </html>
    """
    data = extract_job_from_html(html, base_url="https://fintech.example.com/careers/devops")
    assert "DevOps Lead" in data["title"]
    assert "FinTech Innovations" in data["company"]
    assert "Kubernetes infrastructure" in data["description"]
    assert data["work_mode"] == "remote"
