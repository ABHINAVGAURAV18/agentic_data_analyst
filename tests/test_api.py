import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from test_core import DirectTools

from analyst.api import create_app
from analyst.models import Decision

HEADERS = {"X-API-Key": "test-key"}
PAYLOAD = {"question": "compare sales last month", "as_of": "2026-09-22"}


async def test_api_auth_persistence_isolation(settings, caplog):
    caplog.set_level(logging.INFO, logger="analyst")
    app = create_app(settings, lambda tenant: DirectTools(settings, tenant))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        assert (await c.post("/v1/analyses", json=PAYLOAD)).status_code == 401
        r = await c.post("/v1/analyses", json=PAYLOAD, headers=HEADERS)
        assert r.status_code == 200 and r.json()["status"] == "completed"
        assert r.headers["X-Request-ID"]
        uri = "/v1/analyses/" + r.json()["report_id"]
        assert (await c.get(uri, headers=HEADERS)).json() == r.json()
        assert (await c.get(uri, headers={"X-API-Key": "other-key"})).status_code == 404
        assert (await c.get("/metrics")).status_code == 401
        metrics = await c.get("/metrics", headers=HEADERS)
        assert "analyst_requests_total" in metrics.text
        assert (await c.get("/health/ready")).status_code == 200
        assert "test-key" not in caplog.text and PAYLOAD["question"] not in caplog.text


async def test_real_mcp_end_to_end(settings):
    app = create_app(settings)  # real stdio handshake, discovery and call
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        r = await c.post("/v1/analyses", json=PAYLOAD, headers=HEADERS)
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["status"] == "completed", report
        assert report["evidence"]["current_minor"] == 240000
        assert report["percent_change"] == "-20.00"


async def test_request_deadline(settings):
    class SlowPlanner:
        async def plan(self, question):
            await asyncio.sleep(2)
            return Decision(clarification="late")

    app = create_app(settings.model_copy(update={"request_timeout": 1}), planner=SlowPlanner())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        r = await c.post("/v1/analyses", json=PAYLOAD, headers=HEADERS)
        assert r.status_code == 504


async def test_audit_failure_not_success(settings, monkeypatch):
    app = create_app(settings, lambda tenant: DirectTools(settings, tenant))

    async def broken(*args):
        raise OperationalError("insert", {}, Exception("private database details"))

    monkeypatch.setattr(app.state.audit, "save", broken)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        r = await c.post("/v1/analyses", json=PAYLOAD, headers=HEADERS)
        assert r.status_code == 503 and "private" not in r.text


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "ab"},
        {"question": "x" * 2001},
        {"question": "revenue last month", "tenant": "other"},
    ],
)
async def test_invalid_request(settings, payload):
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        assert (await c.post("/v1/analyses", json=payload, headers=HEADERS)).status_code == 422


async def test_concurrency_limit(settings):
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingPlanner:
        async def plan(self, question):
            entered.set()
            await release.wait()
            return Decision(clarification="Done")

    app = create_app(settings.model_copy(update={"max_concurrency": 1}), planner=WaitingPlanner())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        first = asyncio.create_task(c.post("/v1/analyses", json=PAYLOAD, headers=HEADERS))
        await entered.wait()
        second = await c.post("/v1/analyses", json=PAYLOAD, headers=HEADERS)
        assert second.status_code == 429
        release.set()
        assert (await first).status_code == 200
