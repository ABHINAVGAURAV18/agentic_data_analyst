import hashlib
import json
import time
from collections import OrderedDict

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from analyst.models import Evidence, Plan


class EvidenceCache:
    def __init__(self, url: str | None, ttl: int):
        self.redis = (
            Redis.from_url(url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
            if url
            else None
        )
        self.ttl = ttl
        self.local: OrderedDict[str, tuple[float, str]] = OrderedDict()

    @staticmethod
    def key(tenant: str, revision: str, plan: Plan) -> str:
        raw = json.dumps([tenant, revision, plan.model_dump(mode="json")], sort_keys=True)
        return "evidence:v1:" + hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, key: str) -> Evidence | None:
        try:
            if self.redis:
                value = await self.redis.get(key)
            else:
                expiry, value = self.local.get(key, (0, None))
                if expiry <= time.monotonic():
                    self.local.pop(key, None)
                    return None
            return Evidence.model_validate_json(value) if value else None
        except (RedisError, ValidationError):
            return None

    async def put(self, key: str, value: Evidence):
        try:
            if self.redis:
                await self.redis.set(key, value.model_dump_json(), ex=self.ttl)
            else:
                self.local[key] = (time.monotonic() + self.ttl, value.model_dump_json())
                if len(self.local) > 256:
                    self.local.popitem(last=False)
        except RedisError:
            pass  # Cache is optional; source of truth is the warehouse.

    async def close(self):
        if self.redis:
            await self.redis.aclose()
