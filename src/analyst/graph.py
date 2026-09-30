import asyncio
import hashlib
import json
import random
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from analyst.cache import EvidenceCache
from analyst.config import Settings
from analyst.models import Decision, Evidence, Plan, Question, Report
from analyst.planner import Planner
from analyst.sql import parameters
from analyst.telemetry import CACHE, TOOLS, TRACER
from analyst.tools import ToolFailure


class State(TypedDict, total=False):
    request: Question
    decision: Decision
    evidence: Evidence | None
    attempts: int
    retry: bool
    error: str | None
    cache_hit: bool
    report: Report


def validate_evidence(e: Evidence, plan: Plan, revision: str, tenant: str):
    expected = {k: str(v) for k, v in parameters(plan, tenant).items() if k != "tenant"}
    body = e.model_dump(mode="json", exclude={"evidence_hash"})
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if (
        e.plan != plan
        or e.dataset_revision != revision
        or e.parameters != expected
        or e.sql_template != "sales_by_product_v1"
        or e.evidence_hash != digest
    ):
        raise ValueError("Evidence provenance mismatch")
    if e.current_minor < 0 or (e.previous_minor is not None and e.previous_minor < 0):
        raise ValueError("Revenue cannot be negative in this dataset contract")
    if plan.operation != "revenue" and e.previous_minor is None:
        raise ValueError("Missing comparison baseline")
    if plan.operation == "drivers":
        if (
            sum(p.current_minor for p in e.products) != e.current_minor
            or sum(p.previous_minor for p in e.products) != e.previous_minor
            or any(p.delta_minor != p.current_minor - p.previous_minor for p in e.products)
        ):
            raise ValueError("Product contributions do not reconcile")


def money(minor: int) -> str:
    return f"INR {Decimal(minor) / 100:,.2f}"


def build_graph(settings: Settings, tenant: str, tools, cache: EvidenceCache, planner=None):
    planner = planner or Planner(settings)

    async def plan_node(state: State):
        with TRACER.start_as_current_span("plan"):
            decision = await planner.plan(state["request"])
            return {"decision": decision, "attempts": 0, "cache_hit": False, "error": None}

    async def execute(state: State):
        plan = state["decision"].plan
        key = cache.key(tenant, settings.dataset_revision, plan)
        with TRACER.start_as_current_span("execute"):
            if state["attempts"] == 0:
                cached = await cache.get(key)
                if cached:
                    try:
                        validate_evidence(cached, plan, settings.dataset_revision, tenant)
                        CACHE.labels("hit").inc()
                        return {"evidence": cached, "cache_hit": True, "retry": False}
                    except ValueError:
                        pass
                CACHE.labels("miss").inc()
            attempt = state["attempts"] + 1
            try:
                evidence = await tools.analyze(plan)
                TOOLS.labels("success").inc()
                return {"evidence": evidence, "attempts": attempt, "retry": False, "error": None}
            except ToolFailure as exc:
                TOOLS.labels("failure").inc()
                retry = exc.retryable and attempt < 2
                if retry:
                    await asyncio.sleep(0.1 * attempt + random.uniform(0, 0.1))
                return {
                    "evidence": None,
                    "attempts": attempt,
                    "retry": retry,
                    "error": "The analysis tool is unavailable or could not process this dataset.",
                }

    async def validate(state: State):
        if not state.get("evidence"):
            return {}
        with TRACER.start_as_current_span("validate"):
            try:
                e = state["evidence"]
                validate_evidence(e, state["decision"].plan, settings.dataset_revision, tenant)
                if not state["cache_hit"]:
                    await cache.put(cache.key(tenant, settings.dataset_revision, e.plan), e)
                return {}
            except ValueError:
                return {
                    "evidence": None,
                    "error": "Evidence validation failed; no answer generated.",
                }

    async def report_node(state: State):
        with TRACER.start_as_current_span("report"):
            decision, e = state["decision"], state.get("evidence")
            status, percent = "completed", None
            if decision.clarification:
                status, answer = "needs_clarification", decision.clarification
            elif state.get("error"):
                status, answer = "failed", state["error"]
            elif not e or not e.covered:
                status, answer = (
                    "insufficient_data",
                    (
                        "Coverage is incomplete for the required dates. Supply complete sales data "
                        "before interpreting totals or changes."
                    ),
                )
            else:
                answer = (
                    f"Revenue from {e.plan.start} to {e.plan.end} (exclusive): "
                    f"{money(e.current_minor)}."
                )
                if e.previous_minor is not None:
                    delta = e.current_minor - e.previous_minor
                    answer += (
                        f" Previous equally long period: {money(e.previous_minor)}; "
                        f"change: {money(delta)}."
                    )
                    if e.previous_minor:
                        percent = str(
                            (Decimal(delta) * 100 / Decimal(e.previous_minor)).quantize(
                                Decimal("0.01"), rounding=ROUND_HALF_UP
                            )
                        )
                        answer += f" Percentage change: {percent}%."
                    else:
                        answer += " Percentage change is undefined because the baseline is zero."
                if e.plan.operation == "drivers":
                    ranked = sorted(e.products, key=lambda p: abs(p.delta_minor), reverse=True)[:5]
                    answer += (
                        " Largest product contributions: "
                        + "; ".join(f"{p.product}: {money(p.delta_minor)}" for p in ranked)
                        + "."
                    )
                    answer += (
                        " These are measured contributions, not proven causes. "
                        "Causal analysis needs pricing, promotions, traffic or stock data."
                    )
            return {
                "report": Report(
                    report_id=str(uuid4()),
                    status=status,
                    answer=answer,
                    plan=decision.plan,
                    evidence=e,
                    percent_change=percent,
                    attempts=state["attempts"],
                    cache_hit=state["cache_hit"],
                    planner_mode=settings.planner_mode,
                )
            }

    graph = StateGraph(State)
    for name, fn in [
        ("plan", plan_node),
        ("execute", execute),
        ("validate", validate),
        ("report", report_node),
    ]:
        graph.add_node(name, fn)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", lambda s: "execute" if s["decision"].plan else "report")
    graph.add_conditional_edges("execute", lambda s: "execute" if s.get("retry") else "validate")
    graph.add_edge("validate", "report")
    graph.add_edge("report", END)
    return graph.compile()
