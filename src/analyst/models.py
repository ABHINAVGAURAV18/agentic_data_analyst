from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=2000)
    as_of: date = Field(default_factory=lambda: datetime.now(UTC).date())


class Plan(StrictModel):
    operation: Literal["revenue", "compare", "drivers"]
    start: date
    end: date

    @model_validator(mode="after")
    def bounded_range(self):
        if not 1 <= (self.end - self.start).days <= 366:
            raise ValueError("Use an inclusive start/exclusive end range of 1–366 days")
        return self


class Decision(StrictModel):
    plan: Plan | None = None
    clarification: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.plan is None) == (self.clarification is None):
            raise ValueError("Provide either a plan or clarification")
        return self


class Product(StrictModel):
    product: str
    current_minor: int
    previous_minor: int
    delta_minor: int


class Evidence(StrictModel):
    plan: Plan
    currency: Literal["INR"] = "INR"
    dataset_revision: str
    covered: bool
    current_minor: int
    previous_minor: int | None
    products: list[Product] = Field(default_factory=list)
    sql_template: str
    parameters: dict[str, str]
    evidence_hash: str


class Report(StrictModel):
    report_id: str
    status: Literal["completed", "needs_clarification", "insufficient_data", "failed"]
    answer: str
    plan: Plan | None = None
    evidence: Evidence | None = None
    percent_change: str | None = None
    attempts: int = 0
    cache_hit: bool = False
    planner_mode: str
