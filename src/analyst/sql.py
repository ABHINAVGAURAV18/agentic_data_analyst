from datetime import timedelta

from analyst.models import Plan

# All SQL structure is trusted source code. User/model input is ONLY bound values.
AGGREGATE_SQL = """
SELECT product,
 COALESCE(SUM(CASE WHEN sold_on >= :start AND sold_on < :end
                   THEN revenue_minor ELSE 0 END), 0) AS current_minor,
 COALESCE(SUM(CASE WHEN sold_on >= :previous_start AND sold_on < :start
                   THEN revenue_minor ELSE 0 END), 0) AS previous_minor
FROM sales
WHERE tenant_id = :tenant AND status = 'completed'
 AND sold_on >= :previous_start AND sold_on < :end
GROUP BY product ORDER BY product
LIMIT 101
"""
COVERAGE_SQL = """
SELECT COUNT(*) FROM coverage
WHERE tenant_id = :tenant AND starts_on <= :required_start AND ends_on >= :end
"""


def parameters(plan: Plan, tenant: str) -> dict:
    previous = plan.start - timedelta(days=(plan.end - plan.start).days)
    return {
        "tenant": tenant,
        "start": plan.start,
        "end": plan.end,
        "previous_start": previous if plan.operation != "revenue" else plan.start,
    }
