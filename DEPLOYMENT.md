# CareerPilot AI — Production Deployment & Operations Guide

**Version:** 0.1.0-rc1  
**Architecture:** FastAPI (Async ASGI Backend) + Next.js 16 (Turbopack Frontend) + PostgreSQL (Database & Checkpointer) + Redis (Task Queue & Cache)

---

## 1. Production Architecture Overview

```
[ Client Browser / HTTPS ]
           │
           ▼
[ Reverse Proxy (Nginx / Caddy / Cloudflare) ] ── (TLS Termination, HSTS, Rate Limiting)
           │
     ┌─────┴─────────────────────────┐
     ▼                               ▼
[ Next.js Frontend ]         [ FastAPI Backend ]
  Port: 3000                   Port: 8000
                             (Uvicorn Multi-Worker)
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
         [ PostgreSQL 16+ ]                    [ Redis 7+ ]
         - Database Tables                     - Scheduled Scans
         - LangGraph Checkpointer              - Rate Limit Cache
         - Audit Execution Logs                - Background Tasks
```

---

## 2. Production Environment Variable Reference

Create a secure `.env.production` file on your production host with restricted file permissions (`chmod 600 .env.production`):

```bash
# =========================================================================
# Application Settings
# =========================================================================
APP_ENV=production
APP_NAME="CareerPilot AI"
DEBUG=false
PORT=8000
HOST=0.0.0.0
WORKERS_COUNT=4
FRONTEND_URL=https://app.careerpilot.example.com

# =========================================================================
# Security & Session Authentication
# =========================================================================
# Generate with: openssl rand -hex 32
SECRET_KEY=<REPLACE_WITH_YOUR_STRONG_SECRET_KEY>
ACCESS_TOKEN_EXPIRE_MINUTES=1440
SESSION_MAX_AGE_SECONDS=604800
SESSION_COOKIE_NAME=careerpilot_session

# =========================================================================
# Database (PostgreSQL 16+)
# =========================================================================
POSTGRES_USER=careerpilot_app
POSTGRES_PASSWORD=<REPLACE_WITH_POSTGRES_PASSWORD>
POSTGRES_HOST=db.internal.example.com
POSTGRES_PORT=5432
POSTGRES_DB=careerpilot_prod

# Async connection string used by FastAPI & SQLAlchemy
DATABASE_URL=postgresql+asyncpg://careerpilot_app:<POSTGRES_PASSWORD>@db.internal.example.com:5432/careerpilot_prod

# Sync connection string used by LangGraph checkpointer & migrations
CHECKPOINTER_POSTGRES_URI=postgresql://careerpilot_app:<POSTGRES_PASSWORD>@db.internal.example.com:5432/careerpilot_prod

# =========================================================================
# Distributed Task Queue & Cache (Redis 7+)
# =========================================================================
REDIS_HOST=redis.internal.example.com
REDIS_PORT=6379
REDIS_PASSWORD=<REPLACE_WITH_REDIS_PASSWORD>
REDIS_DB=0
REDIS_URL=redis://:<REDIS_PASSWORD>@redis.internal.example.com:6379/0

# =========================================================================
# AI & LLM Providers (LangChain / LangGraph)
# =========================================================================
OPENAI_API_KEY=<REPLACE_WITH_OPENAI_API_KEY>
ANTHROPIC_API_KEY=<REPLACE_WITH_ANTHROPIC_API_KEY>
GEMINI_API_KEY=<REPLACE_WITH_GEMINI_API_KEY>
PRIMARY_LLM_PROVIDER=openai
FALLBACK_LLM_PROVIDER=anthropic

# LangSmith Observability (PII & Secrets Automatically Redacted)
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<REPLACE_WITH_LANGSMITH_API_KEY>
LANGSMITH_PROJECT=careerpilot-ai-prod

# =========================================================================
# Private Document Storage Root
# =========================================================================
STORAGE_ROOT=/var/lib/careerpilot/data/resumes
```

---

## 3. Database Migration Procedure

Always execute migrations before deploying new application code to ensure schema compatibility:

### 3.1 Pre-Migration Backup
```bash
pg_dump -U careerpilot_app -h db.internal.example.com -d careerpilot_prod -Fc -f "/var/backups/careerpilot/pre_deploy_$(date +%Y%m%d_%H%M%S).dump"
```

### 3.2 Running Migrations
From within the `backend` directory:
```bash
cd /opt/careerpilot/backend
source .venv/bin/activate
alembic upgrade head
```

### 3.3 Verifying Migration Status
```bash
alembic current
alembic heads
```

---

## 4. Automated Backup and Restore Procedure

### 4.1 Daily Automated Backup Script (`/usr/local/bin/backup-careerpilot.sh`)
```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/var/backups/careerpilot"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

mkdir -p "${BACKUP_DIR}/db"
mkdir -p "${BACKUP_DIR}/files"

echo "[$(date)] Starting CareerPilot AI production backup..."

# 1. Backup PostgreSQL Database
pg_dump -U careerpilot_app -h db.internal.example.com -d careerpilot_prod -Fc -f "${BACKUP_DIR}/db/cp_db_${TIMESTAMP}.dump"

# 2. Backup Encrypted CV and Generated Documents Archive
tar -czf "${BACKUP_DIR}/files/cp_resumes_${TIMESTAMP}.tar.gz" -C /var/lib/careerpilot/data/resumes .

# 3. Purge backups older than retention policy
find "${BACKUP_DIR}/db" -type f -name "*.dump" -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}/files" -type f -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete

echo "[$(date)] Backup completed successfully."
```

### 4.2 Point-in-Time Database Restore
```bash
# 1. Stop backend services to prevent concurrent connections
systemctl stop careerpilot-backend careerpilot-worker

# 2. Terminate active database sessions
psql -U postgres -h db.internal.example.com -c "
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
  WHERE datname = 'careerpilot_prod' AND pid <> pg_backend_pid();"

# 3. Restore from binary dump
pg_restore -U postgres -h db.internal.example.com -d careerpilot_prod --clean --if-exists -v "/var/backups/careerpilot/db/cp_db_YYYYMMDD_HHMMSS.dump"

# 4. Restore document file assets
tar -xzf "/var/backups/careerpilot/files/cp_resumes_YYYYMMDD_HHMMSS.tar.gz" -C /var/lib/careerpilot/data/resumes/

# 5. Restart backend services
systemctl start careerpilot-backend careerpilot-worker
```

---

## 5. Health Checks & Worker Failure Handling

### 5.1 Health Check Endpoints
- **Liveness Probe:** `GET https://api.careerpilot.example.com/api/v1/health`  
  Returns `{"status": "ok", "app_name": "CareerPilot AI"}` (HTTP 200).
- **Readiness & Database Probe:** `GET https://api.careerpilot.example.com/api/v1/health/db`  
  Validates PostgreSQL connectivity. Returns `{"database": "healthy", "status": "ok"}`.

### 5.2 Worker Failure Recovery
The background scanner worker (`ScheduledScanWorker`) includes built-in recovery for unexpected process terminations and node outages:
- On startup, `recover_pending_or_stalled_scans(stale_threshold_seconds=900)` discovers scans left in `running` status for longer than 15 minutes.
- Stalled runs are marked `failed` with descriptive diagnostic notes, and distributed scan locks are cleanly released so new scheduled scans resume without administrator intervention.

---

## 6. TLS Termination & Nginx Reverse Proxy Configuration

Install and configure Nginx at `/etc/nginx/sites-available/careerpilot.conf`:

```nginx
server {
    listen 80;
    server_name app.careerpilot.example.com api.careerpilot.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.careerpilot.example.com;

    ssl_certificate /etc/letsencrypt/live/careerpilot.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/careerpilot.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Production Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    client_max_body_size 12M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
    }
}

server {
    listen 443 ssl http2;
    server_name app.careerpilot.example.com;

    ssl_certificate /etc/letsencrypt/live/careerpilot.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/careerpilot.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 7. Incident Response & Secret Rotation Protocol

### 7.1 Secret Rotation Workflow
If credentials (API keys, database passwords, or `SECRET_KEY`) are suspected of compromise:
1. **Rotate Target Key:** Generate new credentials in the respective service dashboard (OpenAI, Anthropic, AWS, or PostgreSQL).
2. **Update `.env.production`:** Insert the new key.
3. **Graceful Reload:**
   ```bash
   systemctl reload-or-restart careerpilot-backend careerpilot-worker
   ```
4. **Session Invalidation:** If `SECRET_KEY` is rotated, execute a database command to revoke all existing active sessions, prompting users to re-authenticate:
   ```sql
   UPDATE user_sessions SET is_revoked = true WHERE is_revoked = false;
   ```

### 7.2 Incident Response Runbook
1. **Identify & Contain:** Inspect logs via `journalctl -u careerpilot-backend -n 100 --no-pager` or query `WorkflowExecutionLog` table.
2. **Isolate:** If an external job provider or webhook behaves unexpectedly, disable the integration via environment variable (`GREENHOUSE_ENABLED=false`) and reload services.
3. **Remediate & Audit:** Review the audit trail in `application_submission_attempts` and `workflow_execution_logs` to verify if any unauthorized submissions occurred.

---

## 8. Known Limitations & Performance Bottlenecks

1. **LLM Generation Latency:**
   - Tailored document generation (resume and cover letter) with automated factual verification takes approximately 2.5–5.0 seconds per document depending on upstream provider API latency (OpenAI / Anthropic).
   - *Mitigation:* Document generation runs asynchronously in background workflow checkpoints, with optimistic UI status updates and instant client resumption.
2. **High-Concurrency Rate Limiting:**
   - The default `InMemoryRateLimiter` enforces sliding-window rate limits per process. In multi-container or Kubernetes replica deployments, requests distributed across different pods track independent windows.
   - *Mitigation:* In distributed setups, enable the Redis-backed distributed rate limiter via `REDIS_URL`.
3. **Job Search Deduplication Load:**
   - Large scheduled scans ingesting thousands of job postings compute similarity hashes and perform URL canonicalization.
   - *Mitigation:* Ingestion is indexed via `UniqueConstraint("source", "source_id")` and `canonical_url` indexes, ensuring $O(1)$ duplicate lookups.
4. **Automated Submission Scope:**
   - Automated direct API submission requires authenticated ATS partner API keys. Requisitions on public job boards without API partner credentials automatically route to the structured manual handoff workflow.

---

## 9. Accessibility & Responsive Layout Standards

- **Semantic HTML5:** All pages use proper semantic landmarks (`<header>`, `<main>`, `<nav>`, `<section>`, `<article>`).
- **Heading Hierarchy:** Strictly enforced single `<h1>` per page with sequential `<h2>` and `<h3>` tags.
- **Color Contrast:** WCAG 2.1 AA compliant color contrast across light and dark modes (slate-950 dark theme with text-slate-100 / text-slate-300 and indigo-400 interactive accents).
- **Responsive Layout:** Fluid responsive layouts built with Tailwind CSS breakpoints (`sm:`, `md:`, `lg:`, `xl:`) supporting viewports from 360px mobile to 4K ultra-wide.
- **Unique Form & Control IDs:** All inputs, modals, and buttons have unique accessible IDs and ARIA labels (`aria-expanded`, `aria-label`, `role="dialog"`).

