# Operations and known limits

## Data contract
- `sales`: one row per order, `revenue_minor` in INR paise; only `completed` counts.
  Cancelled orders are excluded. Refunds and mixed currencies are not supported.
- `coverage`: one interval must fully cover the requested analysis window, including
  the baseline for comparisons. Multiple adjacent intervals are not automatically
  merged. Absence of complete coverage produces `insufficient_data`.
- Product cardinality above 100 causes an explicit tool failure. Do not silently
  truncate totals. Index `(tenant_id, sold_on)` supports bounded date queries.
- Seed is synthetic and idempotent by fixed IDs. It never updates existing rows;
  it is a development utility, not a migration system or production ingestion job.
- Apply the initial SQL migration as an owner. Runtime accounts use separate
  reader/audit roles. Future schema migrations need versioned, reviewed scripts.
- Ingestion must update rows and coverage in one transaction, then advance
  `DATASET_REVISION` in application configuration. A short stale interval until
  deployment/TTL is possible. Strong freshness needs an authoritative revision
  table checked inside the same snapshot; it is not implemented here.

## Authentication and capacity
API keys map to tenant slugs through `API_KEY_HASHES`. Store keys in a secret
manager, distribute outside source control, rotate by briefly accepting old/new
hashes then removing the old hash. This is service-key auth, not end-user SSO.
A tenant shares a single authorization level for read-only analysis and reports.
`/metrics` requires a valid key but exposes service-wide bounded aggregate metrics;
keep scraping internal. Health endpoints expose no credentials or dataset rows.
The concurrency limit is per API process; there is no distributed rate limiting,
per-tenant quota, or gateway/WAF configuration. Run one worker per container and
scale tasks only after testing warehouse capacity.

## Failure behavior
- Invalid request: HTTP 422. Missing/bad API key: 401. Another tenant's report: 404.
- Capacity exhausted: 429 with Retry-After. Overall deadline: 504.
- Audit storage failure: 503. A timeout near commit can be ambiguous: a saved report
  may exist even though the caller received an error. There is no idempotency key.
- Workflow errors return a persisted structured report with status `failed`,
  `insufficient_data`, or `needs_clarification`. Clients must inspect status, not
  infer success from HTTP 200 alone.
- Redis is optional at runtime: connection errors bypass it. Readiness checks both
  required database connections and expected tables, not Redis or a paid LLM.
- Max two tool attempts; DB statement timeout 3s; tool deadline 10s; API deadline
  30s by default. LLM request timeout is 12s; no provider retries.
- Audit reports contain aggregates and product names, but not original questions.
  Restrict access and define a retention policy. v0.1 does not implement deletion
  or retention automation; do maintenance with separately authorized credentials.

## Observability
JSON logs contain server-generated request ID, templated route, status and duration.
Raw questions, keys, DSNs and query rows are not intentionally logged. Uvicorn
access logs are disabled in supplied launch commands to avoid arbitrary URL IDs.
MCP library operational logs may also appear on stderr. Never log raw exceptions
from DB/provider clients without redaction review.

Prometheus: `analyst_requests_total`, `analyst_request_seconds`,
`analyst_reports_total`, `analyst_tool_attempts_total`, `analyst_cache_total`.
Labels are bounded route/status/outcome/planner values, not user IDs or prompts.
Optional `OTLP_ENDPOINT` exports plan/execute/validate/report spans. Export is
opt-in; no remote collector was configured or tested during authoring. These are
node spans, not distributed MCP/database auto-instrumentation. Parent-only test
coverage does not measure code executed in MCP child processes.

Suggested staging alarms (unverified thresholds): elevated 5xx, repeated failed
reports, p95 >10s at the agreed load, sustained 429s, high tool-failure ratio and
RDS/Redis saturation. Set thresholds from an actual baseline before paging.

## Security and production release gates
1. Run PostgreSQL integration tests, Docker build and Compose end-to-end.
2. Review RLS roles, TLS, tenant mapping and secret rotation in staging.
3. Require a passing full CI run and protected production environment approval.
4. Approve provider usage and evaluate >=100 held-out supported/adversarial cases.
5. Load-test 5 concurrent users and measure latency/errors; do not adopt a target
   as an SLA until the hardware, data size and provider are fixed.
6. Configure backup/restore, retention, ingress rate limits and incident ownership.

These are release work still needed, not claims that this repository performed them.
