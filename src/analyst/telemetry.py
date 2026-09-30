import json
import logging

from opentelemetry import trace
from prometheus_client import Counter, Histogram

REQUESTS = Counter("analyst_requests_total", "HTTP requests", ["route", "status"])
LATENCY = Histogram("analyst_request_seconds", "Request duration", ["route"])
REPORTS = Counter("analyst_reports_total", "Report outcomes", ["status", "planner"])
TOOLS = Counter("analyst_tool_attempts_total", "Tool attempts", ["outcome"])
CACHE = Counter("analyst_cache_total", "Evidence cache lookup", ["outcome"])
TRACER = trace.get_tracer("agentic-data-analyst")
logger = logging.getLogger("analyst")


def log_event(event: str, **safe_fields):
    # Call sites supply only request IDs, bounded status labels and durations.
    logger.info(json.dumps({"event": event, **safe_fields}, sort_keys=True))


def setup_tracing(endpoint: str | None):
    if not endpoint:
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "agentic-data-analyst"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    return provider
