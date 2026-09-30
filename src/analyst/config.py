import json
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["development", "production"] = "development"
    warehouse_url: str = "sqlite+aiosqlite:///./demo.db"
    audit_url: str = "sqlite+aiosqlite:///./demo.db"
    redis_url: str | None = None
    # JSON object: sha256(API key) -> tenant slug. No plaintext keys stored here.
    api_key_hashes: str = "{}"
    planner_mode: Literal["demo", "llm"] = "demo"
    allow_external_llm: bool = False
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    dataset_revision: str = "demo-v1"
    cache_ttl: int = Field(default=60, ge=1, le=3600)
    request_timeout: float = Field(default=30, ge=1, le=120)
    tool_timeout: float = Field(default=10, ge=0.1, le=30)
    max_concurrency: int = Field(default=8, ge=1, le=64)
    otlp_endpoint: str | None = None

    @property
    def key_map(self) -> dict[str, str]:
        return json.loads(self.api_key_hashes)

    @model_validator(mode="after")
    def check_settings(self):
        import re

        keys = self.key_map
        if not isinstance(keys, dict) or any(
            not re.fullmatch(r"[0-9a-f]{64}", k)
            or not isinstance(v, str)
            or not re.fullmatch(r"[a-z0-9_-]{1,64}", v)
            for k, v in keys.items()
        ):
            raise ValueError("API_KEY_HASHES must map sha256 hex digests to tenant slugs")
        if self.planner_mode == "llm" and (
            not self.allow_external_llm
            or not self.llm_api_key.get_secret_value()
            or not self.llm_model
            or not self.llm_base_url.startswith("https://")
        ):
            raise ValueError(
                "LLM mode requires explicit external-call opt-in, HTTPS, model and key"
            )
        if self.environment == "production" and (
            not self.warehouse_url.startswith("postgresql+asyncpg://")
            or not self.audit_url.startswith("postgresql+asyncpg://")
            or not self.redis_url
            or not keys
        ):
            raise ValueError("Production requires PostgreSQL URLs, Redis and API key mappings")
        return self
