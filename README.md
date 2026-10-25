# CareerPilot AI — Platform Baseline & Setup Guide

CareerPilot AI is an enterprise-grade AI-powered job discovery and application management platform designed for autonomous matching, agentic cover letter and CV customization, and end-to-end application lifecycle tracking.

---

## Architecture & Technology Stack

- **Frontend**: Next.js 16 (App Router), React 19, TypeScript (Strict Mode), Tailwind CSS v4, Vitest
- **Backend**: Python 3.14 / 3.11+, FastAPI, Pydantic v2, Pydantic Settings
- **AI Orchestration**: LangGraph, LangChain, LangSmith
- **Database & Migrations**: PostgreSQL, SQLAlchemy 2.x, Alembic
- **Background Tasks & Queue**: Redis, ARQ durable task worker
- **Testing & Quality Assurance**: Pytest, Vitest, Playwright, Ruff, Mypy

---

## Repository Structure

```text
careerpilot-ai/
├── .env.example              # Central environment template (placeholders only)
├── .gitignore                # Unified gitignore (ignoring secrets, caches, personal CV data)
├── README.md                 # Project baseline guide & PowerShell setup commands
├── docs/                     # Architectural & specification documentation
│   ├── architecture.md       # System design, dataflow diagram, & components
│   ├── implementation-plan.md# Phased delivery roadmap (Phases 0 to 5)
│   ├── testing-strategy.md   # Testing pyramid, mocking guidelines, and gates
│   └── security.md           # PII handling, security policies, and auth
├── backend/                  # FastAPI service
│   ├── pyproject.toml        # Ruff, Mypy, Pytest tool configurations
│   ├── requirements.txt      # Production dependencies
│   ├── requirements-dev.txt  # Dev/Test dependencies
│   ├── app/                  # Application source package
│   │   ├── main.py           # FastAPI entrypoint
│   │   ├── core/config.py    # Pydantic Settings
│   │   ├── api/v1/router.py  # Health and REST routes
│   │   ├── schemas/health.py # Data validation schemas
│   │   ├── models/           # SQLAlchemy models
│   │   ├── services/         # Domain business logic
│   │   ├── workers/tasks.py  # Async background jobs
│   │   └── integrations/llm.py # Safe local mockable LLM client
│   └── tests/                # Pytest unit & integration tests
└── frontend/                 # Next.js App Router application
    ├── package.json          # Node scripts & dependencies
    ├── tsconfig.json         # Strict TypeScript configuration
    ├── vitest.config.mts     # Vitest runner configuration
    └── src/
        ├── app/              # Next.js App Router pages
        └── __tests__/        # Frontend test suite
```

---

## Windows PowerShell Setup Guide

Execute the following commands in **Windows PowerShell** from the project root (`c:\Users\Abdullah\Desktop\Job Apply Agent`):

### 1. Environment Setup
```powershell
# Copy the environment template
Copy-Item .env.example .env
```

### 2. Backend Setup
```powershell
# Create Python virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install backend dependencies
python -m pip install --upgrade pip
pip install -r backend\requirements-dev.txt

# Run database migrations
cd backend
..\.venv\Scripts\alembic.exe upgrade head
cd ..

# Run development seed script (fictional candidates)
.\.venv\Scripts\python.exe backend\scripts\seed.py

# Run backend static type checks
npx.cmd pyright backend/app --pythonpath .\.venv\Scripts\python.exe

# Run backend tests
.\.venv\Scripts\pytest.exe backend\tests -v
```

### 3. Frontend Setup
```powershell
# Change directory to frontend
Set-Location frontend

# Install dependencies (use npm.cmd in PowerShell to bypass script execution policies)
npm.cmd install

# Run frontend linting
npm.cmd run lint

# Run frontend TypeScript typecheck
npm.cmd run typecheck

# Run frontend unit tests
npm.cmd run test

# Return to root directory
Set-Location ..
```

---

## How to Start the Services Locally

### Start Backend API Server
```powershell
# In PowerShell from root directory:
.\.venv\Scripts\uvicorn app.main:app --app-dir backend --reload --port 8000
```
- API Root: `http://localhost:8000/`
- Health Check: `http://localhost:8000/api/v1/health`
- Interactive API Docs (Swagger): `http://localhost:8000/docs`

### Start Frontend Application
```powershell
# In a separate PowerShell window:
Set-Location frontend
npm.cmd run dev
```
- Frontend UI: `http://localhost:3000`
