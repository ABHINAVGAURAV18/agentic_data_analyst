"""Offline exact-match evaluation. No model or cloud calls. Run from repository root."""

import asyncio
import json
import tempfile
import time
from pathlib import Path

from analyst.cache import EvidenceCache
from analyst.config import Settings
from analyst.graph import build_graph
from analyst.models import Question
from analyst.seed import seed
from analyst.tools import MCPTools


async def main():
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        url = "sqlite+aiosqlite:///" + str(Path(tmp) / "eval.db")
        await seed(url)
        settings = Settings(_env_file=None, warehouse_url=url, audit_url=url)
        cache = EvidenceCache(None, 60)
        for case in json.loads(Path("evals/cases.json").read_text()):
            started = time.monotonic()
            report = (
                await build_graph(
                    settings, case["tenant"], MCPTools(settings, case["tenant"]), cache
                ).ainvoke({"request": Question(question=case["question"], as_of="2026-09-22")})
            )["report"]
            checks = {"status": report.status == case["status"]}
            if "current_minor" in case:
                checks["exact_revenue"] = bool(
                    report.evidence and report.evidence.current_minor == case["current_minor"]
                )
            if "percent_change" in case:
                checks["percent_change"] = report.percent_change == case["percent_change"]
            if "delta_by_product" in case:
                checks["drivers"] = bool(
                    report.evidence
                    and {p.product: p.delta_minor for p in report.evidence.products}
                    == case["delta_by_product"]
                )
                checks["causal_restraint"] = "not proven causes" in report.answer
            results.append(
                {
                    "case": case["id"],
                    "passed": all(checks.values()),
                    "checks": checks,
                    "seconds": round(time.monotonic() - started, 3),
                }
            )
        await cache.close()
    output = {
        "mode": "offline_demo_planner_real_mcp",
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "results": results,
        "limitations": "Small deterministic fixture suite; not live-model accuracy or a load test.",
    }
    Path("evals/latest-results.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    if output["passed"] != output["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
