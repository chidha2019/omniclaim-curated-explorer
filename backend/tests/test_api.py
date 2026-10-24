from datetime import timedelta
from decimal import Decimal

import pytest

from app.auth import Principal, principal
from app.errors import AppError


@pytest.mark.parametrize("path", ["customers", "policies", "claims", "data-health", "me"])
def test_anonymous_denied(client, path):
    r = client.get("/api/v1/" + path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ["customers", "policies", "claims"])
def test_published_contract(client, headers, path):
    r = client.get("/api/v1/" + path, headers=headers)
    assert r.status_code == 200
    assert r.json()["release_id"] and r.json()["as_of"]
    assert r.headers["cache-control"] == "no-store"
    assert len(r.headers["x-trace-id"]) == 32
    assert all("tenant_id" not in item for item in r.json()["items"])


def test_role_denial_precedes_database(client, repo):
    client.app.dependency_overrides[principal] = lambda: Principal("demo", "a", frozenset({"claims"}))
    assert client.get("/api/v1/customers").status_code == 403
    assert repo.calls == 0


def test_pagination_no_duplicate_rows(client, headers):
    items = []
    cursor = None
    for _ in range(4):
        params = {"limit": 20}
        if cursor:
            params["cursor"] = cursor
        r = client.get("/api/v1/customers", headers=headers, params=params).json()
        items.extend(r["items"])
        cursor = r["next_cursor"]
        if not cursor:
            break
    keys = [(r["customer_sk"], r["currency"]) for r in items]
    assert len(keys) == 64 and len(set(keys)) == 64
    assert sum(k[0] == "customer-000" for k in keys) == 2


def test_release_change_requires_restart(client, repo, headers):
    a = client.get("/api/v1/customers", headers=headers).json()
    repo.release = "new-publication"
    r = client.get("/api/v1/customers", headers=headers, params={"cursor": a["next_cursor"]})
    assert r.status_code == 409 and r.json()["code"] == "publication_changed"


def test_cursor_bound_to_filters(client, headers):
    page = client.get("/api/v1/customers", headers=headers).json()
    r = client.get(
        "/api/v1/customers", headers=headers, params={"cursor": page["next_cursor"], "currency": "USD"}
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 101},
        {"limit": 0},
        {"currency": "usd"},
        {"direction": "sideways"},
        {"sort": "FULL_NAME; DROP TABLE x"},
        {"tenant": "other"},
        {"cursor": "invalid"},
    ],
)
def test_reject_invalid_query(client, headers, params):
    r = client.get("/api/v1/customers", params=params, headers=headers)
    assert r.status_code in (400, 422)


def test_filters_and_staleness(client, repo, headers):
    repo.as_of -= timedelta(days=1)
    r = client.get("/api/v1/customers", headers=headers, params={"q": "Avery", "currency": "EUR"}).json()
    assert r["stale"] and len(r["items"]) == 1
    assert r["items"][0]["currency"] == "EUR"
    empty = client.get("/api/v1/customers", headers=headers, params={"q": "not found"}).json()
    assert empty["items"] == [] and empty["release_id"] == repo.release


def test_decimal_precision(client, repo, headers):
    repo.rows["customers"][0]["total_settled_receipts_amt"] = Decimal("9007199254740993.17")
    page = client.get(
        "/api/v1/customers", headers=headers, params={"q": "customer-000", "currency": "USD"}
    ).json()
    assert page["items"][0]["total_settled_receipts_amt"] == "9007199254740993.17"


def test_dependency_failure_redacted(client, repo, headers):
    def fail(*args):
        raise AppError(503, "data_unavailable", "Curated data is temporarily unavailable.")

    repo.page = fail
    r = client.get("/api/v1/customers", headers=headers)
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert "traceback" not in r.text.lower()


def test_unexpected_failure_redacted(client, repo, headers):
    def fail(*args):
        raise RuntimeError("private query with private-customer@example.com")

    repo.page = fail
    r = client.get("/api/v1/customers", headers=headers)
    assert r.status_code == 500 and "private-customer" not in r.text


def test_no_mutation_routes(client, headers):
    assert client.post("/api/v1/claims", headers=headers, json={}).status_code == 405


def test_host_validation(client):
    assert client.get("/health/live", headers={"host": "attacker.invalid"}).status_code == 400


def test_request_body_limit(client, headers):
    assert client.post("/api/v1/telemetry/browser", headers=headers, content=b"x" * 65537).status_code == 413


def test_health(client, headers):
    data = client.get("/api/v1/data-health", headers=headers).json()
    assert not data["stale"] and data["last_attempt_status"] == "SUCCEEDED"
    assert len(data["checks"]) == 3
