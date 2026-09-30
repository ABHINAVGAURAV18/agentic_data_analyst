from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from analyst.models import Report


class AuditStore:
    def __init__(self, url: str):
        self.engine = create_async_engine(url, pool_pre_ping=True)

    async def set_tenant(self, conn, tenant: str):
        if self.engine.dialect.name == "postgresql":
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant}
            )
            await conn.execute(text("SET LOCAL statement_timeout = '3000ms'"))

    async def save(self, tenant: str, report: Report):
        async with self.engine.begin() as conn:
            await self.set_tenant(conn, tenant)
            await conn.execute(
                text("""INSERT INTO reports (id, tenant_id, created_at, payload)
                VALUES (:id, :tenant, :created, :payload)"""),
                {
                    "id": report.report_id,
                    "tenant": tenant,
                    "created": datetime.now(UTC).isoformat(),
                    "payload": report.model_dump_json(),
                },
            )

    async def get(self, tenant: str, report_id: str) -> Report | None:
        async with self.engine.begin() as conn:
            await self.set_tenant(conn, tenant)
            payload = await conn.scalar(
                text("SELECT payload FROM reports WHERE id=:id AND tenant_id=:tenant"),
                {"id": report_id, "tenant": tenant},
            )
        return Report.model_validate_json(payload) if payload else None

    async def ping(self):
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT id, tenant_id, payload FROM reports LIMIT 0"))

    async def close(self):
        await self.engine.dispose()
