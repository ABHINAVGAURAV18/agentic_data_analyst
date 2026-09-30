"""A private stdio server. Tenant and credentials are supplied by the trusted parent."""

import os

from mcp.server.fastmcp import FastMCP
from sqlalchemy.exc import SQLAlchemyError

from analyst.models import Plan
from analyst.warehouse import query_sales

mcp = FastMCP("sales-warehouse")


@mcp.tool()
async def analyze_sales(plan: Plan) -> dict:
    """Read completed INR revenue using a bounded plan and fixed SQL templates."""
    try:
        result = await query_sales(
            os.environ["WAREHOUSE_URL"],
            os.environ["TOOL_TENANT"],
            plan,
            os.environ["DATASET_REVISION"],
        )
        return {"ok": True, "evidence": result.model_dump(mode="json")}
    except SQLAlchemyError:
        return {"ok": False, "retryable": True, "code": "warehouse_unavailable"}
    except ValueError:
        return {"ok": False, "retryable": False, "code": "unsupported_dataset"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
