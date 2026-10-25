# CareerPilot AI — Testing Strategy

## 1. Testing Philosophy
To maintain reliable operation for autonomous agentic actions and high data integrity, CareerPilot AI adopts a rigorous multi-tier test pyramid:

```
          / \
         / E2E \       Playwright (Critical user journeys)
        /-------\
       / Integr. \     Pytest DB/API + Worker integrations
      /-----------\
     /    Unit     \   Pytest (Backend/Agents) & Vitest (Frontend)
    /---------------\
```

---

## 2. Test Suites & Tools

| Tier | Scope | Framework | Execution Command |
|---|---|---|---|
| **Frontend Unit & Component** | React components, utility functions, custom hooks | Vitest + React Testing Library | `npm run test` (in `frontend/`) |
| **Frontend Type & Lint** | Strict type adherence, Next.js lint rules | TypeScript (`tsc`) & ESLint | `npm run typecheck`, `npm run lint` |
| **Backend Unit & Logic** | Schema validation, prompt formatting, parsers | Pytest | `pytest tests/ -m unit` |
| **Backend API & DB** | FastAPI routes, SQLAlchemy async queries, migrations | Pytest + HTTPX + TestContainers/SQLite in-memory | `pytest tests/ -m integration` |
| **AI Determinism & Mocks** | Prompt regression, structured output validation | Pytest + LangChain FakeLLM | `pytest tests/test_agents.py` |
| **End-to-End (E2E)** | Full user onboarding, job search, application flow | Playwright | `npx playwright test` |

---

## 3. Mocking & Deterministic Testing for AI Components
- **Mock LLMs in CI/CD**: Tests must not incur real OpenAI/Anthropic API costs during automated CI builds. LangChain's `FakeListChatModel` or recorded fixtures (vcrpy / pytest-recording) are used for deterministic graph testing.
- **Contract Testing for Schemas**: Pydantic v2 validation ensures all agent outputs adhere to strict schemas before saving into PostgreSQL.

---

## 4. Code Quality & Gatekeeping
Prior to committing code, all pull requests must pass:
1. `backend`:
   - Linting & formatting: `ruff check .` & `ruff format --check .`
   - Static type checking: `mypy app`
   - Automated tests: `pytest`
2. `frontend`:
   - Linting: `npm run lint`
   - Static type checking: `npm run typecheck`
   - Unit tests: `npm run test`
