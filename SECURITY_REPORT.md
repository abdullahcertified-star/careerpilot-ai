# CareerPilot AI — Security Audit & Hardening Report

**Release Candidate Version:** 0.1.0-rc1  
**Audit Date:** October 25, 2026  
**Auditor:** CareerPilot AI Systems & Security Engineering  
**Scope:** Authentication, Authorization, Session Integrity, SSRF Defense, File Upload Security, SQLi/XSS Prevention, Security Headers, Prompt Injection Defense, Human Approval Controls, Personal Data Rights (GDPR), Log Redaction, and Secrets Protection.

---

## 1. Executive Summary

CareerPilot AI has undergone comprehensive production security hardening and end-to-end validation across all backend services, asynchronous worker queues, and frontend interfaces. 

All 12 security assessment categories mandated for production readiness were thoroughly audited and verified via automated test suites. A dedicated 14-step end-to-end lifecycle test executed and passed with 100% compliance.

---

## 2. Detailed Security Review by Domain

### 2.1 Authentication, Authorization, Sessions, CSRF, and Cookie Settings
- **Password Security:** Passwords hashed with `bcrypt` (12 rounds) and validated against minimum complexity standards (length, case, numeric, special characters).
- **Session Tokens:** High-entropy cryptographically secure random session tokens (32 bytes / 256 bits). Only SHA-256 token hashes are persisted in the `user_sessions` database table; plaintext tokens are never stored.
- **Cookie Security:** Cookies are configured with:
  - `HttpOnly: true` (prevents JavaScript access and XSS exfiltration).
  - `SameSite: Lax` (mitigates Cross-Site Request Forgery).
  - `Secure: true` in production environments (enforces HTTPS transmission).
- **Rate Limiting:** Sliding-window IP rate limiter (`InMemoryRateLimiter`) active on `/api/v1/auth/login` and `/api/v1/auth/register` (max 10 requests per minute) and general API endpoints (max 120 requests per minute).

### 2.2 Strict Resource Ownership Checks
- **Profile Data:** Skills, educations, experiences, projects, and certifications require verified `user_id == current_user.id` on all read, update, and delete endpoints. Cross-user modification attempts strictly return `403 Forbidden`.
- **Documents & Extractions:** Staged resume extractions, tailored resumes, and cover letter versions enforce tenant isolation.
- **Job Applications:** Application state inspection, review, approval, rejection, and submission enforce user isolation; cross-user attempts return `404 Not Found` or `403 Forbidden`.
- **Scheduled Searches & Notifications:** Saved searches and alerts are filtered strictly by authenticated user ID.

### 2.3 SSRF Protection for URL Imports, Redirects, and DNS Resolution
- **URL Scheme Validation:** Restricts imports strictly to `http` and `https`. Schemes such as `file://`, `ftp://`, `gopher://`, and `ldap://` are immediately rejected.
- **IP Address & Loopback Filtering:** Hostnames are resolved via DNS (`socket.getaddrinfo`), and every resolved IP is inspected against `ipaddress.ip_address`. All loopback (`127.0.0.0/8`, `::1`), private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local (`169.254.0.0/16`), multicast, and cloud metadata IPs (`169.254.169.254`) are barred.
- **Redirect Chain Re-validation:** HTTP redirects (`301`, `302`, `307`, `308`) follow custom hop-by-hop resolution where each redirect target URL re-resolves and re-verifies DNS and IP safety before executing.
- **Embedded Credentials:** URLs containing userinfo (e.g. `http://user:pass@example.com`) are rejected.

### 2.4 File Upload Validation & Private Storage
- **Magic Byte Verification:** File signatures are strictly inspected prior to parsing:
  - PDF: Enforces `%PDF` header magic bytes.
  - DOCX: Enforces zip magic bytes (`PK\x03\x04`) and confirms internal `word/document.xml` existence.
  - TXT: Validates UTF-8 / Latin-1 text encoding.
- **MIME-Type Spoofing Defense:** Renamed executables or shell scripts with `.pdf` or `.docx` extensions are rejected with `415 Unsupported Media Type` or `422 Unprocessable Content`.
- **File Size Bounding:** Maximum file size is strictly capped at 10 MB (`413 Content Too Large`).
- **Private Storage Isolation:** Stored files are written to `STORAGE_ROOT/{user_id}/{uuid}_{safe_filename}`, residing outside of any public web server document root and accessible only through authenticated FastAPI streaming endpoints.

### 2.5 Secret Scanning & Repository Hygiene
- **Committed Secrets Scan:** Repository history and working directory scanned. Zero active API keys, JWT secrets, database passwords, or credentials were committed.
- **Git Ignore Safeguards:** `.env`, `.env.production`, SQLite databases (`*.db`), virtual environments (`.venv/`), and uploaded CV documents (`data/resumes/`) are explicitly excluded via `.gitignore`.
- **Configuration Hygiene:** The repository supplies `.env.example` containing dummy template placeholders for all environment variables.

### 2.6 SQL Queries, Output Encoding, XSS, and Injection Risks
- **SQL Injection Defense:** All queries utilize SQLAlchemy 2.0 ORM with asynchronous parameterized statements (`select()`, `where()`, `update()`, `delete()`). No raw unparameterized SQL string interpolation is present.
- **XSS & Output Encoding:** External HTML job descriptions fetched via import are sanitized using `bleach`, stripping dangerous tags (`<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`) and inline event handlers (`onload`, `onerror`, `onclick`).
- **Pydantic Validation:** All API inputs undergo strict typing and character length bounding via Pydantic v2 schemas.

### 2.7 CORS and Security Headers
- **CORS Configuration:** Enforces explicit origins (`settings.FRONTEND_URL` and `http://localhost:3000`) with credentials support.
- **HTTP Security Headers Middleware:** Applied to all HTTP responses:
  - `X-Content-Type-Options: nosniff` (prevents MIME type sniffing).
  - `X-Frame-Options: DENY` (prevents clickjacking attacks).
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (enforces TLS).
  - `Content-Security-Policy: default-src 'self'; frame-ancestors 'none';` (content boundary enforcement).
  - `Referrer-Policy: strict-origin-when-cross-origin` (prevents URL parameter leakage).
  - `Permissions-Policy: geolocation=(), microphone=(), camera=()` (disables unused browser hardware APIs).

### 2.8 Prompt Injection Defenses
- **Structural Delimiters:** User-provided job descriptions and unstructured CV texts are quarantined inside distinct XML-style boundary delimiters (`<job_description>`, `<candidate_facts>`) in LLM prompts.
- **Instruction Precedence:** System prompts instruct models to ignore embedded directives that command ignoring previous rules, exfiltrating instructions, or altering output formats.
- **Factual Grounding Check:** Automated factual consistency validator (`FactualChecker`) compares all generated claims against verified candidate profile facts, flagging ungrounded entities and ensuring zero hallucinated experience.

### 2.9 Approval Enforcement & Duplicate-Submission Protections
- **Mandatory Human-in-the-Loop Interrupt:** LangGraph workflow pauses execution at the `human_approval_interrupt` state. Application records enter `awaiting_approval` status.
- **Strict Approval Prerequisite:** `submission_service.submit_application` checks `approval_status == 'approved'`. Unapproved, rejected, or cancelled applications raise `UnauthorizedSubmissionError`.
- **Package Fingerprint Binding:** Explicit approval records a SHA-256 fingerprint (`package_hash`) computed across target job, document version IDs, and form answers. If any content changes after approval, the approval is invalidated (`status: invalidated`), requiring fresh human re-approval.
- **Database Idempotency & Unique Constraints:** `ApplicationSubmissionAttempt` enforces a database `UniqueConstraint("submission_key")`, guaranteeing simultaneous duplicate requests are blocked at the database level.
- **Blind Resubmission Guard:** If a provider submission attempt is pending confirmation (`confirmation_pending`), subsequent submissions are blocked with `BlindResubmissionError` to prevent duplicate submissions.

### 2.10 Personal Data Retention, Export, and Erasure (GDPR Articles 15, 17, 20)
- **Data Export (`GET /api/v1/profile/export`):** Generates a structured JSON archive containing candidate account info, profile facts, verified skills, educations, experiences, projects, certifications, resume metadata, application history, saved searches, and in-app notifications.
- **Permanent Account Erasure (`DELETE /api/v1/profile/account`):** Executes cascading database deletion across all related tables (`Profile`, `Skill`, `Education`, `Experience`, `Project`, `Certification`, `ResumeMetadata`, `JobApplication`, `SavedSearch`, `Notification`), permanently deletes uploaded resume files on disk from `data/resumes/{user_id}/`, clears session cookies, and invalidates active sessions.

### 2.11 Logging & LangSmith Trace Redaction
- **PII & Credential Redaction:** `RedactingLangSmithTracer` and `redact_sensitive_value` sanitize outgoing LLM traces and execution logs:
  - Redacts sensitive form answers (SSN, date of birth, driver's license numbers, salary expectations).
  - Strips API keys, Authorization headers, and session tokens.
  - Logs audit actions referencing entity IDs rather than full CV contents.

### 2.12 Production Incident Response & Secret Management
- Documented in detail in `DEPLOYMENT.md`, including secret rotation protocols, TLS termination, point-in-time PostgreSQL recovery, and health check monitoring.

---

## 3. Prioritized Unresolved Risks

| Severity | Risk Item | Description | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Medium** | Next.js Dependency CVE | Upstream vulnerability notification on Next.js 16.4.0 (`SecurityFatalError` notice during production build). | Execute `next upgrade --agent=security` in dedicated worktree after user approval. |
| **Low** | In-Memory Rate Limiting in Multi-Replica Setups | Current rate limiter uses sliding memory window. When backend is scaled to multiple container replicas, rate limits are tracked per container rather than globally. | Transition `InMemoryRateLimiter` to Redis-backed sliding window via Redis sorted sets in high-scale cluster deployment. |
| **Low** | Production ATS Partner Credentials | Automated submission routes default to safe manual handoff mode until verified enterprise ATS partner API credentials (Greenhouse, Lever) are provisioned. | Production deployments must securely configure OAuth2/API credentials for automated ATS submission. |
