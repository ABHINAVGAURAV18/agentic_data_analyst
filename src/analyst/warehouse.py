import hashlib
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from analyst.models import Evidence, Plan, Product
from analyst.sql import AGGREGATE_SQL, COVERAGE_SQL, parameters


async def query_sales(url: str, tenant: str, plan: Plan, revision: str) -> Evidence:
    engine = create_async_engine(url, pool_pre_ping=True)
    params = parameters(plan, tenant)
    if engine.dialect.name == "sqlite":
        params = {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in params.items()}
    try:
        async with engine.connect() as conn, conn.begin():
            if engine.dialect.name == "postgresql":
                await conn.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
                await conn.execute(text("SET LOCAL statement_timeout = '3000ms'"))
                await conn.execute(
                    text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant}
                )
            elif engine.dialect.name == "sqlite":
                await conn.execute(text("PRAGMA query_only = ON"))
            covered = bool(
                await conn.scalar(
                    text(COVERAGE_SQL), {**params, "required_start": params["previous_start"]}
                )
            )
            rows = (await conn.execute(text(AGGREGATE_SQL), params)).mappings().all()
        if len(rows) > 100:
            raise ValueError(
                "Product cardinality exceeds v0.1 limit; do not return truncated totals"
            )
        products = [
            Product(
                product=r["product"],
                current_minor=int(r["current_minor"]),
                previous_minor=int(r["previous_minor"]),
                delta_minor=int(r["current_minor"] - r["previous_minor"]),
            )
            for r in rows
        ]
        body = dict(
            plan=plan.model_dump(mode="json"),
            dataset_revision=revision,
            covered=covered,
            currency="INR",
            current_minor=sum(p.current_minor for p in products),
            previous_minor=(
                sum(p.previous_minor for p in products) if plan.operation != "revenue" else None
            ),
            products=[p.model_dump() for p in products] if plan.operation == "drivers" else [],
            sql_template="sales_by_product_v1",
            parameters={k: str(v) for k, v in params.items() if k != "tenant"},
        )
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        return Evidence(**body, evidence_hash=digest)
    finally:
        await engine.dispose()
