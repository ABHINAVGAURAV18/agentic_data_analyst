# Agentic Data Analyst

A production-oriented, bounded sales analyst built with **Python, FastAPI,
LangGraph, MCP, PostgreSQL, Redis, Docker and AWS deployment configurations**.
It answers revenue questions with validated database evidence and explains product
contributions without inventing business causes.

**Status:** functional local v0.1. Demo planning works without paid APIs. An opt-in
OpenAI-compatible planner is implemented and mock-tested; live-model quality is
not measured. This is a portfolio foundation, not a claim of production certification.
See [verification](docs/VERIFICATION.md) for exactly what ran and what did not.

## Start locally (Windows PowerShell, macOS or Linux)
Prerequisites: Python 3.11–3.13 and uv. Commands run from this folder.

```sh
uv sync --frozen
python scripts/bootstrap.py
uv run python -m analyst.seed
uv run uvicorn analyst.api:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal in the same folder:

```sh
uv run python scripts/demo.py
```

Browse **http://127.0.0.1:8000/docs** for the interactive API. Click **Authorize**
and enter `DEMO_API_KEY` from the generated `.env` file. The server stores only
its SHA-256 mapping; never commit `.env`. A local SQLite database is used in this
quickstart. It does not provide PostgreSQL RLS and must not be used in production.
Bootstrap refuses to overwrite an existing `.env`.

Example request:
```json
{"question":"why did sales change last month","as_of":"2026-09-22"}
```
The fixture result is August revenue **INR 2,400**, July revenue **INR 3,000**,
change **−20.00%**. Gadget contributes **−INR 1,100** and Widget **+INR 500**.
These values come from synthetic seed data, not real company metrics.

Supported offline prompts:
- `revenue last month`
- `compare sales last month`
- `why did sales change last month`

Use `as_of: 2026-09-22` for the sample. Other questions ask for clarification in
demo mode. Comparison means the immediately preceding **equally long period**,
not necessarily the preceding calendar month. Dates are UTC; end is exclusive.

## Run the intended PostgreSQL + Redis topology
Requires Docker Engine/Desktop with Compose:

```sh
python scripts/bootstrap.py
# Skip bootstrap if .env already exists.
docker compose up --build -d
uv run python scripts/demo.py
docker compose logs api
```

The one-shot seed container adds only synthetic data. Fresh PostgreSQL initialization
creates separate reader and audit roles and forced row-level security. Databases
have no host port mapping; only the API binds to localhost. `docker compose down`
keeps data. **`docker compose down -v` deletes the local database volume.** Never
use the demo seed service against a production warehouse. This Compose topology
has not been run in the authoring environment because Docker is unavailable.

## What is implemented
- API-key authentication with server-owned tenant mapping; per-process concurrency
  bound, request deadlines, input validation, report persistence and retrieval.
- LangGraph plan → execute/retry → validate → report workflow with at most two
  tool attempts and jittered backoff for retryable failures.
- Real MCP stdio discovery and typed tool invocation, with restricted child-process
  credentials. MCP v1 is deliberately pinned to the tested API family.
- Typed semantic plan → fixed parameterized SQL. No endpoint or tool accepts raw SQL.
- PostgreSQL least-privilege roles, RLS, read-only/repeatable-read tool transactions,
  statement timeouts, tenant filters, coverage checks and bounded product cardinality.
- Redis evidence caching by tenant/plan/revision/TTL, graceful cache-outage bypass.
- Financial values in integer paise; deterministic reports, source parameters and
  evidence hashes; no unsupported causal claims.
- JSON operational logs, Prometheus metrics and optional OpenTelemetry spans.
- Tests, offline evaluations, Docker, GitHub Actions CI and approval-gated ECS CD.

## Verification commands
```sh
uv run ruff check src tests evals scripts
uv run ruff format --check src tests evals scripts
uv run pytest --cov=analyst --cov-report=term-missing
uv run python evals/run.py
```
Without disposable service URLs, integration tests explicitly skip. CI configures
PostgreSQL 16 and Redis 7 and runs them. See `tests/test_postgres.py` for required
`TEST_*_URL` variables. These tests install schema/fixtures and use a disposable
Redis DB; never point them at existing business data.

`evals/latest-results.json` is a measured result from the checked-in small offline
suite. It is **not live-model accuracy**, a production benchmark or an SLA.

## Optional LLM planner
After separately approving provider usage, configure `.env`:
```dotenv
PLANNER_MODE=llm
ALLOW_EXTERNAL_LLM=true
LLM_BASE_URL=https://your-approved-provider.example/v1
LLM_MODEL=your-approved-model
LLM_API_KEY=your-secret
```
The provider must support `/chat/completions`, JSON-object response format and
`max_tokens`. Provider compatibility varies; contract tests use mocks. The planner
receives the question and `as_of`, not database credentials or query results.
The typed plan still passes the same deterministic guards. No model provider was
called while building this project. Keep private information out of questions
unless its transmission is approved.

## Documentation and learning path
1. [Architecture, acceptance criteria and milestones](docs/ARCHITECTURE.md)
2. [Interview explanations and engineering tradeoffs](docs/INTERVIEW.md)
3. [Operations, data contract and limitations](docs/OPERATIONS.md)
4. [AWS prerequisites and controlled deployment](infra/aws/README.md)
5. [Actual verification results](docs/VERIFICATION.md)

The code is organized by those boundaries under `src/analyst/`. Read `models.py`,
`planner.py`, `sql.py`, `warehouse.py`, `mcp_server.py`, `tools.py`, `graph.py`, then
`api.py`. Save a report with `POST /v1/analyses` and retrieve it with
`GET /v1/analyses/{report_id}` using the same tenant's API key.

## Portfolio publishing
After reviewing the archive and confirming `.env` is ignored:
```sh
git init
git add .
git commit -m "Build bounded agentic sales analyst with evaluation and deployment configs"
git branch -M main
```
Create your own empty GitHub repository, add its remote and push when ready.
Nothing has been published on your behalf. Do not claim the skipped PostgreSQL
checks, hosted CI, live-model evaluation or AWS deployment have passed until you
have their results.
