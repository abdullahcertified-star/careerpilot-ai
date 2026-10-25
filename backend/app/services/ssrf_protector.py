"""SSRF protection utility and safe HTTP client for external URL fetching."""

import ipaddress
import socket
import urllib.parse
from typing import List, Optional, Set, Tuple
import httpx


class SSRFSecurityError(Exception):
    """Raised when an external URL targets a prohibited, private, or loopback network address."""
    pass


# Specific prohibited CIDRs
PROHIBITED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),    # Loopback IPv4
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / Cloud metadata (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),  # Private IPv4
    ipaddress.ip_network("192.0.0.0/24"),   # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),   # Documentation (TEST-NET-1)
    ipaddress.ip_network("192.168.0.0/16"), # Private IPv4
    ipaddress.ip_network("198.18.0.0/15"),  # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),# Documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"), # Documentation (TEST-NET-3)
    ipaddress.ip_network("224.0.0.0/4"),    # Multicast
    ipaddress.ip_network("240.0.0.0/4"),    # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6
    ipaddress.ip_network("::1/128"),        # Loopback IPv6
    ipaddress.ip_network("::/128"),         # Unspecified
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),   # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),       # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
    ipaddress.ip_network("fc00::/7"),       # Unique local address (ULA)
    ipaddress.ip_network("fe80::/10"),      # Link-local IPv6
    ipaddress.ip_network("ff00::/8"),       # Multicast IPv6
]

MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
DEFAULT_TIMEOUT_SECONDS = 8.0


def validate_and_resolve_url(url_str: str) -> Tuple[str, List[str]]:
    """
    Validates scheme and resolves hostname.
    Ensures all resolved IP addresses are public, non-private, non-loopback destinations.
    Returns (cleaned_url, list_of_resolved_ips).
    Raises SSRFSecurityError if any violation is detected.
    """
    if not url_str or not isinstance(url_str, str):
        raise SSRFSecurityError("URL must be a non-empty string.")

    cleaned_url = url_str.strip()
    try:
        parsed = urllib.parse.urlsplit(cleaned_url)
    except Exception as exc:
        raise SSRFSecurityError(f"Malformed URL: {exc}") from exc

    # 1. Scheme check
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSecurityError(
            f"Prohibited URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    # 2. Hostname check
    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityError("URL is missing a valid hostname.")

    # Reject userinfo in URL authority (e.g. http://user:pass@example.com)
    if parsed.username or parsed.password:
        raise SSRFSecurityError("User credentials in URL authority are not permitted.")

    # 3. DNS resolution & IP check
    resolved_ips: List[str] = []
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_infos:
            ip_str = str(sockaddr[0])
            if ip_str not in resolved_ips:
                resolved_ips.append(ip_str)
    except socket.gaierror as exc:
        raise SSRFSecurityError(f"Failed to resolve hostname '{hostname}': {exc}") from exc
    except Exception as exc:
        raise SSRFSecurityError(f"DNS resolution error for '{hostname}': {exc}") from exc

    if not resolved_ips:
        raise SSRFSecurityError(f"No IP addresses resolved for hostname '{hostname}'.")

    # 4. Verify every resolved IP
    for ip_str in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SSRFSecurityError(f"Invalid resolved IP '{ip_str}': {exc}") from exc

        # Check standard properties
        if (
            ip_obj.is_loopback
            or ip_obj.is_private
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            raise SSRFSecurityError(
                f"Prohibited network destination: '{hostname}' resolved to restricted IP '{ip_str}'."
            )

        # Check explicit subnet masks (including IPv4-mapped IPv6)
        if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
            mapped_ipv4 = ip_obj.ipv4_mapped
            if (
                mapped_ipv4.is_loopback
                or mapped_ipv4.is_private
                or mapped_ipv4.is_link_local
            ):
                raise SSRFSecurityError(
                    f"Prohibited network destination: IPv4-mapped IPv6 '{ip_str}' points to restricted IPv4 '{mapped_ipv4}'."
                )

        for network in PROHIBITED_NETWORKS:
            if ip_obj in network:
                raise SSRFSecurityError(
                    f"Prohibited network destination: '{hostname}' ({ip_str}) matches restricted subnet {network}."
                )

    return cleaned_url, resolved_ips


async def safe_fetch_url(
    url_str: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> Tuple[str, str, dict]:
    """
    Safely fetches the given URL with comprehensive SSRF protection,
    per-hop redirect IP re-validation, bounded size, and timeout.
    
    Returns (final_canonical_url, response_text, response_headers).
    """
    current_url, _ = validate_and_resolve_url(url_str)
    redirect_count = 0

    headers = {
        "User-Agent": "CareerPilotAI/1.0 (+https://careerpilot.ai; JobImportEngine)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        while True:
            # Re-validate before each request (including redirects)
            validate_and_resolve_url(current_url)

            try:
                response = await client.get(current_url, headers=headers)
            except httpx.TimeoutException as exc:
                raise TimeoutError(f"Request to '{current_url}' timed out after {timeout_seconds}s.") from exc
            except httpx.RequestError as exc:
                raise ConnectionError(f"HTTP request failed: {exc}") from exc

            # Check redirect status codes (301, 302, 303, 307, 308)
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                if redirect_count > MAX_REDIRECTS:
                    raise SSRFSecurityError(f"Exceeded maximum allowed redirects ({MAX_REDIRECTS}).")

                location = response.headers.get("location")
                if not location:
                    raise SSRFSecurityError("Redirect response missing 'Location' header.")

                # Resolve relative redirect URLs safely against current_url
                next_url = urllib.parse.urljoin(current_url, location)
                # Re-validate destination of redirect hop
                current_url, _ = validate_and_resolve_url(next_url)
                continue

            # Non-redirect response: check status
            if response.status_code != 200:
                raise ValueError(
                    f"Remote server returned HTTP {response.status_code} ({response.reason_phrase})."
                )

            # Check Content-Length if present
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError(
                    f"Remote content exceeds maximum allowed size ({int(content_length)} > {max_bytes} bytes)."
                )

            # Check actual content length
            content = response.content
            if len(content) > max_bytes:
                raise ValueError(
                    f"Downloaded content exceeds limit of {max_bytes} bytes."
                )

            text_content = response.text
            return current_url, text_content, dict(response.headers)
