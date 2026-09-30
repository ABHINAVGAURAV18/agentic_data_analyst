import asyncio
import json
import os
import sys
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from analyst.config import Settings
from analyst.models import Evidence, Plan


class ToolFailure(Exception):
    def __init__(self, code: str, retryable: bool = False):
        super().__init__(code)
        self.retryable = retryable


class MCPTools:
    def __init__(self, settings: Settings, tenant: str):
        self.settings, self.tenant = settings, tenant

    async def analyze(self, plan: Plan) -> Evidence:
        env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if k in os.environ}
        env.update(
            WAREHOUSE_URL=self.settings.warehouse_url,
            TOOL_TENANT=self.tenant,
            DATASET_REVISION=self.settings.dataset_revision,
        )
        server = StdioServerParameters(
            command=sys.executable, args=["-m", "analyst.mcp_server"], env=env
        )
        try:
            async with asyncio.timeout(self.settings.tool_timeout):
                async with stdio_client(server) as (read, write):
                    async with ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=8)
                    ) as session:
                        await session.initialize()
                        available = await session.list_tools()
                        if "analyze_sales" not in [t.name for t in available.tools]:
                            raise ToolFailure("missing_tool")
                        result = await session.call_tool(
                            "analyze_sales", {"plan": plan.model_dump(mode="json")}
                        )
                        if result.isError:
                            raise ToolFailure("invalid_tool_response")
                        payload = result.structuredContent
                        if payload is None:
                            payload = json.loads(
                                next(c.text for c in result.content if c.type == "text")
                            )
                        if not payload.get("ok"):
                            raise ToolFailure(
                                payload.get("code", "tool_failed"), payload.get("retryable", False)
                            )
                        return Evidence.model_validate(payload["evidence"])
        except ToolFailure:
            raise
        except TimeoutError as exc:
            raise ToolFailure("tool_timeout", True) from exc
        except Exception as exc:
            # anyio task groups may wrap transport or tool errors in ExceptionGroup.
            failures = []

            def collect(error):
                if isinstance(error, ToolFailure):
                    failures.append(error)
                for child in getattr(error, "exceptions", []):
                    collect(child)

            collect(exc)
            if failures:
                raise failures[0] from exc
            raise ToolFailure("tool_transport_failed", True) from exc
