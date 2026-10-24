"""Synthetic records for LOCAL/TEST only. Never source these from real customer CSVs."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .errors import AppError
from .models import Query
from .sql import order_columns


class FixtureRepository:
    def __init__(self):
        self.release = "demo-release-2026-10-24"
        self.as_of = datetime.now(UTC) - timedelta(minutes=18)
        self.calls = 0
        self.rows = {
            "customers": [
                dict(
                    customer_sk=f"customer-{i:03}",
                    full_name=f"{['Avery Morgan', 'Riley Chen', 'Jordan Patel', 'Taylor Brooks', 'Casey Rivera'][i % 5]} {i:02}",
                    client_category_cd=["INDIVIDUAL", "HNW", "FAMILY"][i % 3],
                    age=30 + i % 35,
                    primary_territory=["North Carolina", "New York", "Massachusetts"][i % 3],
                    primary_contact_method="EMAIL",
                    primary_contact_value=f"customer{i}@example.invalid",
                    currency="USD",
                    total_settled_receipts_amt=Decimal("1250.50") * (i + 1),
                )
                for i in range(63)
            ],
            "policies": [
                dict(
                    snapshot_date=self.as_of.date(),
                    product_group_sk=f"product-{i:02}",
                    lob_cd=["LIFE", "DI", "LTC", "ANNUITY"][i % 4],
                    product_name=["Whole Life", "Disability Income", "Long-Term Care", "Fixed Annuity"][
                        i % 4
                    ],
                    currency="USD" if i < 5 else "EUR",
                    active_policy_count=124 + i * 19,
                    active_current_term_amt=Decimal("381250.25") * (i + 1),
                    new_active_policies=3 + i,
                )
                for i in range(8)
            ],
            "claims": [
                dict(
                    loss_event_sk=f"loss-{i:03}",
                    lob_cd=["LIFE", "DI", "LTC"][i % 3],
                    loss_type_cd=["DEATH", "DISABILITY", "LONG_TERM_CARE"][i % 3],
                    claim_status_cd=["UNDER_REVIEW", "PAID", "APPROVED", "OPEN"][i % 4],
                    currency="USD",
                    days_to_report=i % 12,
                    days_to_last_payment=14 + i % 8 if i % 4 == 1 else None,
                    settled_amount=Decimal("18000.50") if i % 4 == 1 else Decimal("0.00"),
                    paid_to_term_premium_ratio=Decimal("0.35") if i % 4 == 1 else None,
                )
                for i in range(38)
            ],
        }
        # Same person in a second currency deliberately exercises the declared customer grain.
        self.rows["customers"].append(
            {**self.rows["customers"][0], "currency": "EUR", "total_settled_receipts_amt": Decimal("800.00")}
        )

    def page(
        self,
        dataset: str,
        tenant: str,
        pipeline: str,
        role: str,
        query: Query,
        release: str | None,
        offset: int,
    ):
        self.calls += 1
        order_columns(dataset, query)
        if release and release != self.release:
            raise AppError(
                409, "publication_changed", "A new data release is available. Refresh to restart browsing."
            )
        from .datasets import DATASETS

        rows = [
            r.copy()
            for r in self.rows[dataset]
            if (not query.currency or r["currency"] == query.currency)
            and (
                not query.q
                or any(query.q.lower() in str(r.get(k.lower(), "")).lower() for k in DATASETS[dataset].search)
            )
        ]
        # Stable secondary keys first, then requested primary sort.
        rows.sort(key=lambda r: tuple(str(r.get(k.lower()) or "") for k in DATASETS[dataset].keys))
        if query.sort != "default":
            key = query.sort.lower()
            nonnull = [r for r in rows if r.get(key) is not None]
            nonnull.sort(key=lambda r: r[key], reverse=query.direction == "desc")
            rows = nonnull + [r for r in rows if r.get(key) is None]
        return rows[offset : offset + query.limit + 1], self.release, self.as_of

    def health(self, tenant: str, pipeline: str, role: str):
        return dict(
            tenant_id=tenant,
            pipeline_id=pipeline,
            active_release_id=self.release,
            active_as_of=self.as_of,
            published_at=self.as_of + timedelta(minutes=4),
            last_attempt_at=self.as_of,
            last_attempt_status="SUCCEEDED",
            last_error_code=None,
            run_id="demo-run-001",
            run_status="SUCCEEDED",
            checks=[
                dict(layer=layer, check_name=c, failures=0)
                for layer, c in [
                    ("BRONZE", "source_contract"),
                    ("SILVER", "referential_integrity"),
                    ("GOLD", "currency_reconciliation"),
                ]
            ],
        )

    def close(self):
        pass
