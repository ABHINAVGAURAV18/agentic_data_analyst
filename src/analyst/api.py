import asyncio
import hashlib
import hmac
import logging
import time
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from analyst.cache import EvidenceCache
from analyst.config import Settings
from analyst.graph import build_graph
from analyst.models import Question, Report
from analyst.storage import AuditStore
from analyst.telemetry import LATENCY, REPORTS, REQUESTS, log_event, setup_tracing
from analyst.tools import MCPTools

key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_app(settings: Settings | None = None, tool_factory=None, planner=None):
    settings = settings or Settings()
    cache = EvidenceCache(settings.redis_url, settings.cache_ttl)
    audit = AuditStore(settings.audit_url)
    semaphore = asyncio.Semaphore(settings.max_concurrency)

    @asynccontextmanager
    async def lifespan(app):
        logging.basicConfig(level=logging.INFO)
        # Avoid logging outbound URLs or request payloads from client libraries.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        provider = setup_tracing(settings.otlp_endpoint)
        yield
        await cache.close()
        await audit.close()
        if provider:
            await asyncio.to_thread(provider.shutdown)

    app = FastAPI(title="Agentic Data Analyst", version="0.1.0", lifespan=lifespan)
    app.state.cache, app.state.audit = cache, audit

    async def tenant(api_key: str | None = Security(key_header)):
        digest = hashlib.sha256((api_key or "").encode()).hexdigest()
        for stored, identity in settings.key_map.items():
            if hmac.compare_digest(digest, stored):
                return identity
        raise HTTPException(401, "Valid API key required")

    @app.middleware("http")
    async def observe(request, call_next):
        request_id, started = str(uuid4()), time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            label = route.path if route else "unmatched"
            elapsed = time.monotonic() - started
            REQUESTS.labels(label, str(status)).inc()
            LATENCY.labels(label).observe(elapsed)
            log_event(
                "http_request",
                request_id=request_id,
                route=label,
                status=status,
                duration_ms=round(elapsed * 1000, 2),
            )

    @app.get("/health/live")
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready():
        engine = create_async_engine(settings.warehouse_url)
        try:
            async with asyncio.timeout(4):
                await audit.ping()
                async with engine.connect() as conn:
                    await conn.execute(
                        text("SELECT tenant_id, sold_on, revenue_minor FROM sales LIMIT 0")
                    )
            return {"status": "ready"}
        except (SQLAlchemyError, TimeoutError, OSError):
            raise HTTPException(503, "Required database unavailable") from None
        finally:
            await engine.dispose()

    @app.get("/metrics", dependencies=[Depends(tenant)])
    async def metrics():
        return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    @app.post("/v1/analyses", response_model=Report)
    async def analyze(request: Question, identity: str = Depends(tenant)):
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
        except TimeoutError:
            raise HTTPException(
                429, "Analysis capacity reached; retry later", headers={"Retry-After": "2"}
            ) from None
        try:
            async with asyncio.timeout(settings.request_timeout):
                tools = tool_factory(identity) if tool_factory else MCPTools(settings, identity)
                graph = build_graph(settings, identity, tools, cache, planner)
                result = await graph.ainvoke({"request": request}, config={"recursion_limit": 12})
                report = result["report"]
                await audit.save(identity, report)
                REPORTS.labels(report.status, settings.planner_mode).inc()
                return report
        except TimeoutError:
            raise HTTPException(504, "Analysis deadline exceeded") from None
        except SQLAlchemyError:
            raise HTTPException(503, "Audit storage unavailable; result not committed") from None
        finally:
            semaphore.release()

    @app.get("/v1/analyses/{report_id}", response_model=Report)
    async def get_report(report_id: UUID, identity: str = Depends(tenant)):
        try:
            report = await audit.get(identity, str(report_id))
        except SQLAlchemyError:
            raise HTTPException(503, "Report storage unavailable") from None
        if not report:
            raise HTTPException(404, "Report not found")
        return report

    return app
