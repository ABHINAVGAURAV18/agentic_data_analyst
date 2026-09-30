import asyncio

import fakeredis.aioredis
import httpx
import pytest
from pydantic import ValidationError
from test_core import PLAN

from analyst.cache import EvidenceCache
from analyst.config import Settings
from analyst.models import Question
from analyst.planner import Planner
from analyst.warehouse import query_sales


async def test_redis_ttl_isolation(settings):
    cache = EvidenceCache(None, 1)
    cache.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    e = await query_sales(settings.warehouse_url, "acme", PLAN, "demo-v1")
    key = cache.key("acme", "demo-v1", PLAN)
    await cache.put(key, e)
    assert await cache.get(key) == e
    assert await cache.get(cache.key("other", "demo-v1", PLAN)) is None
    assert await cache.get(cache.key("acme", "demo-v2", PLAN)) is None
    await asyncio.sleep(1.05)
    assert await cache.get(key) is None
    await cache.close()


async def test_redis_outage_bypass(settings):
    cache = EvidenceCache("redis://127.0.0.1:1", 60)
    assert await cache.get("key") is None
    e = await query_sales(settings.warehouse_url, "acme", PLAN, "demo-v1")
    await cache.put("key", e)
    await cache.close()


def test_production_settings_fail_closed():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, planner_mode="llm", llm_api_key="x")


@pytest.mark.parametrize(
    "content,valid",
    [
        ('{"plan":{"operation":"revenue","start":"2026-08-01","end":"2026-09-01"}}', True),
        ('{"plan":{"operation":"delete","start":"2026-08-01","end":"2026-09-01"}}', False),
        ("not json", False),
        (
            '{"plan":{"operation":"revenue","start":"2026-08-01","end":"2026-09-01","tenant":"other"}}',
            False,
        ),
    ],
)
async def test_provider_contract_mock_only(monkeypatch, content, valid):
    async def post(self, url, **kwargs):
        assert kwargs["json"]["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": content}}]},
        )

    class MockClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    MockClient.post = post
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    settings = Settings(
        _env_file=None,
        planner_mode="llm",
        allow_external_llm=True,
        llm_api_key="test-only",
        llm_model="mock",
    )
    result = await Planner(settings).plan(Question(question="revenue last month"))
    assert (result.plan is not None) == valid


@pytest.mark.integration
async def test_real_redis(settings):
    import os

    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("Disposable Redis not configured")
    cache = EvidenceCache(url, 1)
    e = await query_sales(settings.warehouse_url, "acme", PLAN, "demo-v1")
    key = cache.key("acme", "integration", PLAN)
    try:
        await cache.put(key, e)
        assert await cache.get(key) == e
        assert 0 <= await cache.redis.ttl(key) <= 1
        assert await cache.get(cache.key("other", "integration", PLAN)) is None
        await asyncio.sleep(1.05)
        assert await cache.get(key) is None
    finally:
        await cache.close()
