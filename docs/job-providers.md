# CareerPilot AI — Job Provider Integration Architecture & Status

This document defines the provider adapter architecture, permissions, access tiers, and security constraints for job discovery in CareerPilot AI.

## Provider Integration Matrix & Status

| Provider | Integration Type | Status | Required Permissions / Auth | Direct Scraping Permitted? |
| :--- | :--- | :--- | :--- | :--- |
| **Greenhouse Job Board** | Direct Public REST API | **VERIFIED LIVE API** | Public endpoints (`/v1/boards/{board_token}/jobs`), No API key required for open boards. | N/A (Official REST API) |
| **Manual URL Import** | Dedicated Secure Ingestion | **VERIFIED SECURE IMPORT** | Public web page with valid HTTP(S), SSRF protection, strict HTML sanitization. | N/A (Single-URL user action) |
| **LinkedIn Jobs** | Link-First Portal Generator | **LINK-FIRST ONLY** | Authenticated user session on linkedin.com. Prohibited without LinkedIn Enterprise Partner API. | **NO (Strictly Prohibited)** |
| **Indeed** | Link-First Portal Generator | **LINK-FIRST ONLY** | Prohibited without Indeed Publisher / XML Partner API agreement. | **NO (Strictly Prohibited)** |
| **Lever (Future)** | Direct Public REST API | *Planned Phase 4* | Public Career Site API (`/v0/postings/{company}`). | N/A (Official REST API) |
| **Workday (Future)** | Deep-Link / XML Feed | *Planned Phase 4* | Enterprise tenant API or authenticated job portal. | **NO** |

---

## 1. Architecture Overview

CareerPilot AI adopts an extensible adapter pattern with strict capability separation:

```
                      +-----------------------------+
                      |     JobProvider (ABC)       |
                      +-----------------------------+
                      | + capabilities()            |
                      | + search()                  |
                      | + fetch_details()           |
                      | + normalize()               |
                      +-----------------------------+
                                     ▲
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
+-------------------+       +-------------------+       +-------------------+
| GreenhouseAdapter |       | LinkedInAdapter   |       | IndeedAdapter     |
| (Live REST API)   |       | (Link-First Only) |       | (Link-First Only) |
+-------------------+       +-------------------+       +-------------------+
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     ▼
                      +-----------------------------+
                      |     JobProviderRegistry     |
                      |  - Error Isolation          |
                      |  - Deduplication Engine     |
                      |  - Rate Limits & Retries    |
                      +-----------------------------+
```

### Core Abstractions
1. **`ProviderCapabilities`**: Declares whether the adapter supports direct API search, details retrieval, URL import, link-first portal generation, rate limits, and external search templates.
2. **`JobSearchQuery`**: Standardized criteria including keywords, location, work mode (`remote`, `hybrid`, `onsite`), board tokens, and pagination parameters.
3. **`NormalizedJob`**: Canonical schema ensuring consistent normalization across heterogeneous sources.
4. **`JobSearchResult`**: Normalized listing bundle containing pagination state, provider attribution, warnings, and optional fallback deep links.

---

## 2. Greenhouse Job Board Integration (Verified Live API)

- **API Base**: `https://boards-api.greenhouse.io/v1/boards/{board_token}`
- **Authentication**: None required for publicly published job boards.
- **Operations**:
  - `GET /v1/boards/{board_token}/jobs?content=true`: Lists open requisitions with HTML job content, department, office location, and updated timestamps.
  - `GET /v1/boards/{board_token}/jobs/{job_id}`: Retrieves comprehensive single job requisition details.
- **Resilience**:
  - Configurable timeout: 10 seconds.
  - Rate limiting: Client-side token bucket (60 requests/minute default).
  - Bounded retries: 3 attempts with exponential backoff on HTTP 429 or 5xx responses.
  - Error isolation: Upstream Greenhouse failures or individual board 404s log warnings and do not crash concurrent searches.

---

## 3. Link-First Integrations: LinkedIn & Indeed

### Policy & Compliance
- **No Unauthorized Scraping**: CareerPilot AI strictly adheres to platform terms of service, robots.txt directives, and access policies. Neither LinkedIn nor Indeed are scraped directly.
- **Link-First Behavior**:
  - Generates query-parameterized deep-search URLs (e.g. `https://www.linkedin.com/jobs/search/?keywords=...&location=...&f_WT=2`).
  - Instructs the candidate to review listings in their authenticated browser session.
  - Allows the candidate to paste individual posting URLs into the **Manual URL Importer** for structured ingestion and local profile matching.

---

## 4. Manual URL Import & SSRF Protection Architecture

The manual URL ingestion pipeline implements defense-in-depth against Server-Side Request Forgery (SSRF) and untrusted document payloads:

1. **Protocol & Scheme Whitelisting**:
   - Only `http://` and `https://` schemes are permitted. Rejects `file://`, `ftp://`, `gopher://`, `data:`, `javascript:`, etc.
2. **Destination & DNS Resolution Verification**:
   - The destination hostname is resolved to IPv4 and IPv6 addresses via `socket.getaddrinfo`.
   - Every resolved IP is evaluated against prohibited subnets using `ipaddress`:
     - Loopback (`127.0.0.0/8`, `::1`)
     - Private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
     - Link-local & cloud metadata (`169.254.0.0/16`, `fe80::/10`)
     - Carrier-grade NAT (`100.64.0.0/10`)
     - Multicast, broadcast, unspecified (`0.0.0.0/8`, `224.0.0.0/4`, `240.0.0.0/4`)
3. **Redirect Hop Inspection**:
   - Redirects are NOT followed blindly. Each hop URL is parsed, validated, and its target IP resolved and re-verified.
   - Redirect chains are bounded to a maximum of 3 hops.
4. **Payload Constraints & Sanitization**:
   - Maximum download size: 2 MB.
   - Timeout: 8 seconds.
   - HTML Sanitization: Strips `<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>`, inline event handlers (`onclick`, etc.).
   - Untrusted Text Isolation: Content is treated purely as untrusted text. Embedded instructions or prompt injection attempts are never treated as system instructions.

---

## 5. Storage & Deduplication Engine

Discovered and imported jobs are stored in `job_postings` with deduplication:
1. **Source Key Deduplication**: Compound index on `(source, source_id)`. If a requisition already exists from that provider, it is updated in-place with the latest timestamp.
2. **Canonical URL Deduplication**: URLs are canonicalized by stripping query tracking parameters (`utm_*`, `ref`, `trk`, `source`) and trailing slashes. Duplicate URLs update existing entries.
3. **User Bookmarking**: Users can bookmark jobs via `saved_jobs` with per-user ownership and status tracking (`saved`, `applied`, `interviewing`, `rejected`).
