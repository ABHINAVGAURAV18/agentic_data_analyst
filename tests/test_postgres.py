"""Run with TEST_ADMIN_URL / TEST_READER_URL / TEST_AUDIT_URL / TEST_REDIS_URL.
Use a disposable database: the fixture installs the initial schema and demo data.
"""

import os
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from test_api import HEADERS, PAYLOAD

from analyst.api import create_app
from analyst.seed import seed

pytestmark = pytest.mark.integration


@pytest.fixture
async def pg_settings(settings):
    admin = os.getenv("TEST_ADMIN_URL")
    if not admin:
        pytest.skip("Disposable PostgreSQL service not configured")
    conn = await asyncpg.connect(admin.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        if not await conn.fetchval("SELECT to_regclass('public.sales')"):
            await conn.execute(Path("infra/postgres/001-schema.sql").read_text())
            await conn.execute("ALTER ROLE analyst_reader PASSWORD 'test-reader'")
            await conn.execute("ALTER ROLE analyst_audit PASSWORD 'test-audit'")
    finally:
        await conn.close()
    await seed(admin)
    return settings.model_copy(
        update={
            "warehouse_url": os.environ["TEST_READER_URL"],
            "audit_url": os.environ["TEST_AUDIT_URL"],
            "redis_url": os.environ["TEST_REDIS_URL"],
        }
    )


async def test_real_postgres_mcp_redis(pg_settings):
    app = create_app(pg_settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        await app.state.cache.redis.flushdb()  # disposable test Redis only
        r = await c.post("/v1/analyses", json=PAYLOAD, headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed", r.text
        assert r.json()["evidence"]["current_minor"] == 240000
        again = await c.post("/v1/analyses", json=PAYLOAD, headers=HEADERS)
        assert again.json()["cache_hit"]
        assert (
            await c.get("/v1/analyses/" + r.json()["report_id"], headers=HEADERS)
        ).status_code == 200


async def test_rls_without_application_filter_and_write_denial(pg_settings):
    engine = create_async_engine(pg_settings.warehouse_url)
    try:
        async with engine.begin() as conn:
            assert await conn.scalar(text("SELECT COUNT(*) FROM sales")) == 0
            await conn.execute(text("SELECT set_config('app.tenant_id','acme',true)"))
            tenants = (
                (await conn.execute(text("SELECT DISTINCT tenant_id FROM sales"))).scalars().all()
            )
            assert tenants == ["acme"]
            role = (
                await conn.execute(
                    text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                )
            ).one()
            assert role == (False, False)
        async with engine.begin() as conn:
            with pytest.raises(Exception, match="(?i)(read.only|permission denied)"):
                await conn.execute(text("DELETE FROM sales"))
    finally:
        await engine.dispose()


async def test_audit_rls(pg_settings):
    engine = create_async_engine(pg_settings.audit_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.tenant_id','other',true)"))
            with pytest.raises(Exception, match="row-level security"):
                await conn.execute(text("INSERT INTO reports VALUES ('bad','acme','now','{}')"))
    finally:
        await engine.dispose()
