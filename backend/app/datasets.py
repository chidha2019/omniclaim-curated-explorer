from dataclasses import dataclass

from .models import Claim, Customer, PolicyMetric


@dataclass(frozen=True)
class DatasetSpec:
    view: str
    columns: tuple[str, ...]
    keys: tuple[str, ...]
    search: tuple[str, ...]
    sorts: tuple[str, ...]
    model: type


DATASETS = {
    "customers": DatasetSpec(
        "APP_CUSTOMERS",
        (
            "CUSTOMER_SK",
            "FULL_NAME",
            "CLIENT_CATEGORY_CD",
            "AGE",
            "PRIMARY_TERRITORY",
            "PRIMARY_CONTACT_METHOD",
            "PRIMARY_CONTACT_VALUE",
            "CURRENCY",
            "TOTAL_SETTLED_RECEIPTS_AMT",
        ),
        ("CUSTOMER_SK", "CURRENCY"),
        ("FULL_NAME", "CUSTOMER_SK", "PRIMARY_TERRITORY"),
        ("FULL_NAME", "TOTAL_SETTLED_RECEIPTS_AMT"),
        Customer,
    ),
    "policies": DatasetSpec(
        "APP_POLICIES",
        (
            "SNAPSHOT_DATE",
            "PRODUCT_GROUP_SK",
            "LOB_CD",
            "PRODUCT_NAME",
            "CURRENCY",
            "ACTIVE_POLICY_COUNT",
            "ACTIVE_CURRENT_TERM_AMT",
            "NEW_ACTIVE_POLICIES",
        ),
        ("SNAPSHOT_DATE", "PRODUCT_GROUP_SK", "CURRENCY"),
        ("PRODUCT_NAME", "LOB_CD"),
        ("PRODUCT_NAME", "ACTIVE_POLICY_COUNT", "ACTIVE_CURRENT_TERM_AMT"),
        PolicyMetric,
    ),
    "claims": DatasetSpec(
        "APP_CLAIMS",
        (
            "LOSS_EVENT_SK",
            "LOB_CD",
            "LOSS_TYPE_CD",
            "CLAIM_STATUS_CD",
            "CURRENCY",
            "DAYS_TO_REPORT",
            "DAYS_TO_LAST_PAYMENT",
            "SETTLED_AMOUNT",
            "PAID_TO_TERM_PREMIUM_RATIO",
        ),
        ("LOSS_EVENT_SK",),
        ("LOSS_EVENT_SK", "LOB_CD", "CLAIM_STATUS_CD"),
        ("SETTLED_AMOUNT", "DAYS_TO_REPORT", "CLAIM_STATUS_CD"),
        Claim,
    ),
}
