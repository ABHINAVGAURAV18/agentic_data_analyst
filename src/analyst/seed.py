"""Create deterministic development data. Never call against production."""

import argparse
import asyncio
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from analyst.config import Settings

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL, sold_on DATE NOT NULL,
        product VARCHAR(80) NOT NULL, revenue_minor BIGINT NOT NULL CHECK (revenue_minor >= 0),
        status VARCHAR(20) NOT NULL CHECK (status IN ('completed','cancelled')))""",
    "CREATE INDEX IF NOT EXISTS sales_tenant_date ON sales (tenant_id, sold_on)",
    """CREATE TABLE IF NOT EXISTS coverage (
        tenant_id VARCHAR(64) NOT NULL, starts_on DATE NOT NULL, ends_on DATE NOT NULL,
        PRIMARY KEY (tenant_id, starts_on), CHECK (starts_on < ends_on))""",
    """CREATE TABLE IF NOT EXISTS reports (
        id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
        created_at VARCHAR(40) NOT NULL, payload TEXT NOT NULL)""",
]
ROWS = [
    (1, "acme", date(2026, 7, 15), "Widget", 100000, "completed"),
    (2, "acme", date(2026, 7, 20), "Gadget", 200000, "completed"),
    (3, "acme", date(2026, 8, 15), "Widget", 150000, "completed"),
    (4, "acme", date(2026, 8, 20), "Gadget", 90000, "completed"),
    (5, "acme", date(2026, 8, 25), "Gadget", 999999, "cancelled"),
    (6, "other", date(2026, 8, 20), "Private", 9900000, "completed"),
    (7, "zero", date(2026, 8, 15), "Widget", 10000, "completed"),
]


async def seed(url: str):
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            for ddl in SCHEMA:
                await conn.execute(text(ddl))
            for row in ROWS:
                if engine.dialect.name == "sqlite":
                    row = tuple(v.isoformat() if isinstance(v, date) else v for v in row)
                await conn.execute(
                    text("""INSERT INTO sales
                    (id, tenant_id, sold_on, product, revenue_minor, status)
                    VALUES (:id,:tenant,:day,:product,:revenue,:status)
                    ON CONFLICT (id) DO NOTHING"""),
                    dict(
                        zip(
                            ["id", "tenant", "day", "product", "revenue", "status"],
                            row,
                            strict=True,
                        )
                    ),
                )
            for tenant in ["acme", "other", "zero", "empty"]:
                await conn.execute(
                    text("""INSERT INTO coverage (tenant_id,starts_on,ends_on)
                    VALUES (:tenant,:start,:end) ON CONFLICT (tenant_id,starts_on) DO NOTHING"""),
                    {
                        "tenant": tenant,
                        "start": date(2026, 7, 1)
                        if engine.dialect.name == "postgresql"
                        else "2026-07-01",
                        "end": date(2026, 9, 1)
                        if engine.dialect.name == "postgresql"
                        else "2026-09-01",
                    },
                )
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Development database owner URL")
    args = parser.parse_args()
    settings = Settings()
    if settings.environment != "development":
        raise SystemExit("Seeding is disabled outside development")
    asyncio.run(seed(args.url or settings.warehouse_url))
    print("Development schema and sample data ready.")


if __name__ == "__main__":
    main()
