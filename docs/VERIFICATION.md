# Verification record

Authoring session: 2026-09-22. Linux, Python 3.12.14, uv 0.12.17.
Exact resolved dependency versions and hashes are in `uv.lock`.

## Executed and observed
| Check | Actual result |
|---|---|
| Dependency resolution/installation | `uv sync --frozen --offline --inexact` succeeded after dependency downloads; editable project installed |
| Lock consistency | `uv lock --check --offline` passed |
| Ruff lint | Passed for src, tests, evals and scripts |
| Ruff format | Passed for all 22 Python files at final check |
| Pytest with local Redis | **40 passed, 3 skipped**; 6.91 seconds for that run |
| Parent-process statement coverage | **88% rounded**; does not instrument MCP child processes |
| Offline evaluation | **12/12 passed**, deterministic demo planner, real MCP stdio, SQLite fixture |
| Real HTTP smoke | Uvicorn → authenticated HTTP API → LangGraph → MCP subprocess → SQLite → saved report succeeded |
| Fixture smoke output | 240000 paise current revenue, 300000 baseline, −20.00% change |
| Redis integration | Real Redis server round-trip, tenant-key separation, TTL and expiry passed |
| Configuration syntax | Compose, both GitHub workflows and CloudFormation parsed as YAML |

The Redis test service used a locally bundled Redis executable. CI targets Redis 7;
no claim of having run that exact Redis 7 container locally. See `TEST-OUTPUT.txt`,
`coverage.json`, `example-report.json` and `../evals/latest-results.json`.
Per-case evaluation durations are observations on tiny fixtures, not a latency SLA.

## Explicitly not verified
- **Three PostgreSQL integration tests skipped.** Docker is absent. A bundled
  PostgreSQL setup was attempted, but the runtime denies changing system users or
  groups, so PostgreSQL could not start. PostgreSQL RLS, grants, read-only transaction
  behavior and asyncpg integration are prepared for CI, not claimed as passing.
- Docker image build and Compose startup were not run.
- GitHub-hosted CI and CD were not run. No repository was created or pushed.
- CloudFormation was parsed, not AWS-validated or deployed. No paid cloud resources
  or external service settings were changed.
- The live LLM planner was only exercised with mock HTTP responses. No paid model
  calls, provider quality measurements or held-out model evaluation were performed.
- OTLP export to a collector, distributed tracing, load/scalability tests, database
  TLS, image vulnerability scanning, failover and backup/restore remain unverified.

## Errors found and resolved
- Initial build dependency download timed out. An available tested hatchling version
  was pinned and downloaded; editable installation and lock checks subsequently passed.
- Four provider-contract tests initially failed while constructing an HTTP client
  with the environment's proxy configuration. They now fully mock the client so
  tests cannot depend on network/proxy state or contact a provider.
- SQLite date adapter deprecation warnings were removed by binding ISO dates in
  the development dialect; PostgreSQL continues to bind Python date values.
- Lint/format issues were corrected and checks rerun.

## What the evidence does and does not establish
The tested local implementation answers the defined sales questions with exact
fixture results and handles the covered failure paths. It establishes neither
production readiness nor open-ended analyst quality. Complete the outstanding
PostgreSQL/Compose gates first, then obtain approval for provider/cloud validation.
