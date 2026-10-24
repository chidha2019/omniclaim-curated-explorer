from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Row(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Customer(Row):
    customer_sk: str
    full_name: str | None = None
    client_category_cd: str | None = None
    age: int | None = None
    primary_territory: str | None = None
    primary_contact_method: str | None = None
    primary_contact_value: str | None = None
    currency: str | None = None
    total_settled_receipts_amt: Decimal


class PolicyMetric(Row):
    snapshot_date: date
    product_group_sk: str
    lob_cd: str | None = None
    product_name: str | None = None
    currency: str
    active_policy_count: int
    active_current_term_amt: Decimal
    new_active_policies: int


class Claim(Row):
    loss_event_sk: str
    lob_cd: str | None = None
    loss_type_cd: str | None = None
    claim_status_cd: str | None = None
    currency: str
    days_to_report: int | None = None
    days_to_last_payment: int | None = None
    settled_amount: Decimal
    paid_to_term_premium_ratio: Decimal | None = None


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None
    release_id: str
    as_of: datetime
    stale: bool


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(default="", max_length=100)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    sort: str = Field(default="default", max_length=50)
    direction: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=4096)


class QualityCheck(BaseModel):
    layer: str
    check_name: str
    failures: int


class HealthStatus(BaseModel):
    tenant_id: str
    pipeline_id: str
    active_release_id: str | None
    active_as_of: datetime | None
    published_at: datetime | None
    last_attempt_at: datetime | None
    last_attempt_status: str | None
    last_error_code: str | None
    run_id: str | None
    run_status: str | None
    checks: list[QualityCheck]
    stale: bool


class BrowserSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal[
        "GET /api/v1/customers", "GET /api/v1/policies", "GET /api/v1/claims", "GET /api/v1/data-health"
    ]
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    start_ns: int = Field(gt=0)
    duration_ns: int = Field(ge=0, le=120_000_000_000)
    error: bool


class BrowserBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spans: list[BrowserSpan] = Field(max_length=20)
