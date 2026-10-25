# CareerPilot AI — Security & Privacy Architecture

## 1. Core Security Principles
CareerPilot AI handles sensitive personally identifiable information (PII) including candidate resumes, employment history, contact details, and application credentials. Security and privacy are primary architectural constraints.

---

## 2. Secrets Management & Environment Isolation
- **No Secrets in Code**: No API keys, passwords, or encryption secrets may be committed to Git.
- **Unified Configuration**: All environment configurations load from `.env` (ignored by Git) guided by `.env.example`.
- **Validation**: Pydantic's `BaseSettings` verifies required environment variables upon startup and fails fast if any configuration is missing or malformed in production.

---

## 3. Data Protection & Resume Privacy
1. **PII Masking & Sanitization**:
   - Before submitting candidate resumes to third-party LLMs, optional PII scrubbing removes national IDs, home addresses, and phone numbers when matching skills.
2. **Encrypted Storage**:
   - Uploaded resumes and generated artifacts are stored securely in local volume storage or S3-compatible object stores with encryption at rest (AES-256).
3. **Candidate Consent Gate (Human-in-the-Loop)**:
   - The AI agent is prohibited from autonomously submitting job applications without explicit candidate confirmation. Every tailored application produces a draft requiring approval.

---

## 4. API & Network Security
- **Authentication**: JWT (JSON Web Tokens) with short expiry (e.g. 15-60 minutes) and refresh token rotation.
- **CORS Protection**: Explicit origin whitelisting (`FRONTEND_URL`) preventing cross-origin abuse.
- **Rate Limiting**: Redis-backed token bucket rate limiting on authentication and LLM-triggering endpoints to protect against DDoS and denial-of-wallet attacks.
- **SQL Injection Prevention**: Exclusive usage of SQLAlchemy 2.x parameterized async queries.
- **Input Validation**: Strict Pydantic v2 schemas validating all incoming payloads before processing.
