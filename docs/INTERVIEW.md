# Defending the design in an AI Engineer interview

## Two-minute explanation
“I built a bounded Agentic Data Analyst for sales revenue investigation. A user
asks a question through a FastAPI endpoint. The planner produces a typed plan
containing an operation and dates. LangGraph coordinates planning, MCP tool
execution, bounded retries, evidence validation and report generation.

“The MCP server reads a curated PostgreSQL dataset through fixed parameterized
SQL. The model never gets a raw SQL execution tool. Tenant identity is derived
from authentication, and the database applies row-level security in addition to
application filters. Monetary values use integer minor units. Before returning
an answer, I validate dataset coverage and reconcile product contributions.

“Redis caches validated evidence with tenant and data-revision isolation.
PostgreSQL separately persists completed report snapshots. I added structured
logs, Prometheus metrics, OpenTelemetry spans and deterministic evaluation cases.
The project includes Docker and ECS deployment configuration. I distinguish the
checks I actually ran from PostgreSQL, cloud and live-model checks still requiring
a suitable environment.”

Use the verification report for actual counts. This is a project explanation,
not a claim that it served enterprise traffic or produced business savings.

## Likely cross-questions
| Question | Defensible answer |
|---|---|
| Why LangGraph? | Explicit state and conditional edges make retry budgets and failure paths inspectable. A linear pipeline would also work for basic totals; the graph becomes useful when validation and recovery branch. |
| Is it actually agentic? | LLM mode chooses a supported plan from the question; execution and recovery use a bounded graph. Offline demo mode is deterministic. It is not an autonomous general SQL analyst. |
| Why restrict SQL? | A semantic plan lets the model choose intent while code controls executable syntax. Parameters are values, never identifiers. This trades breadth for a testable security boundary. |
| What prevents cross-tenant reads? | API-key mapping fixes the tenant; MCP gets it from the parent environment. SQL filters and forced RLS both apply. The configured role must not own tables or bypass RLS. |
| Is RLS sufficient alone? | No. A compromised backend with reader credentials could choose a different tenant setting. It protects against omitted filters, not a fully compromised trusted server. |
| Why MCP? | It separates the orchestration client from a discoverable, schema-defined tool server. MCP itself does not supply authorization; we supply that trust boundary. |
| Why stdio? | It keeps this tool local with no network listener. A new process per cache miss is simple to isolate but adds startup cost. A persistent authenticated service would need lifecycle and authorization design. |
| Why FastAPI async? | Model, cache and database calls wait on I/O. Async permits overlapping waits. It does not make SQL faster or replace limits on concurrent work. |
| Why not use the LLM for arithmetic? | Code can calculate and reconcile exact numbers. The model's role is interpreting intent, not inventing totals. |
| How do you evaluate? | Exact ground-truth totals, deltas, product changes, status and isolation assertions first; provider output validation with mocks; live intent accuracy needs a separate held-out set and approved calls. |
| Why no LLM-as-judge score? | These tasks have objective numeric and safety targets. A subjective judge should not replace exact reconciliation. It can supplement narrative evaluation later. |
| Why Redis and PostgreSQL? | Redis is a disposable TTL evidence cache. PostgreSQL is the durable source of business data and report snapshots. |
| What if Redis fails? | Query the warehouse and continue. The deadline and concurrency bound still apply. If audit persistence fails, return an explicit error rather than a success without its saved report. |
| How do you prevent stale cache results? | Cache keys include dataset revision and a short TTL. Ingestion must atomically update the data/coverage and publish a new revision to the app. This is an operational contract, not automatic CDC. |
| How do you explain a revenue drop? | Reconcile product contributions. Do not infer causation from sales rows alone; ask for promotions, stock, traffic or pricing data. |
| How do retries work? | Only retryable tool failures trigger a second attempt with jitter. Invalid plans do not retry. The API imposes an overall deadline. |
| What if the process crashes? | Completed reports persist; in-flight graphs do not resume. This v0.1 does not claim durable checkpointing or exactly-once execution. |
| Why ECS instead of EKS? | This service does not yet need Kubernetes. Fargate simplifies running the API and local tool process. EKS becomes relevant if the deployment organization already standardizes on Kubernetes. |
| What makes it production-oriented? | Explicit boundaries, failure behavior, measurable gates, least privilege, telemetry and deployment preparation. Production-ready would additionally require staging verification, live evaluation, load testing, backup drills and operational ownership. |

## What to build next
After the existing PostgreSQL/Compose gates pass, approve and evaluate one real
model against held-out paraphrases, ambiguous periods and adversarial requests.
Then add explicit previous-calendar-month comparisons, ingestion/version
management, SSO/RBAC, durable jobs/checkpoints and additional allowlisted metrics.
Each new metric needs a business definition and gold examples before expansion.
