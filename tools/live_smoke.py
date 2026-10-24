"""No fixture fallback. Exercise deployed OIDC, API, real Snowflake views and telemetry.
SMOKE_CONFIG points to a Jenkins Secret File. Never prints tokens or customer records.
"""

import json
import os
import time
from pathlib import Path

import httpx

config = json.loads(Path(os.environ["SMOKE_CONFIG"]).read_text())
base = config["base_url"].rstrip("/")
prom = config["prometheus_url"].rstrip("/")
if not all(u.startswith("https://") for u in [base, prom, config["token_endpoint"]]):
    raise SystemExit("HTTPS required")
clients = config["clients"]
if len({c["tenant"] for c in clients}) < 2:
    raise SystemExit("At least two independently entitled test tenants are required")
paths = {
    "customers": "customers",
    "policies": "policies",
    "claims": "claims",
    "health": "data-health",
}
with httpx.Client(timeout=45, verify=True, follow_redirects=False) as http:
    runtime = http.get(base + "/api/v1/config")
    runtime.raise_for_status()
    assert runtime.json()["demo"] is False, "Deployed system must never serve fixtures"
    assert http.get(base + "/api/v1/customers").status_code == 401
    for identity in clients:
        response = http.post(
            config["token_endpoint"],
            data={
                "grant_type": "client_credentials",
                "client_id": identity["client_id"],
                "client_secret": identity["client_secret"],
                "scope": identity.get("scope", "omniclaim.read"),
            },
        )
        assert response.status_code == 200, "Unable to obtain test identity token"
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        who = http.get(base + "/api/v1/me", headers=headers)
        who.raise_for_status()
        assert who.json()["tenant"] == identity["tenant"]
        assert set(who.json()["capabilities"]) == set(identity["capabilities"])
        for cap, path in paths.items():
            res = http.get(
                base + "/api/v1/" + path,
                headers=headers,
                params={"limit": 1} if cap != "health" else None,
            )
            assert res.status_code == (
                200 if cap in identity["capabilities"] else 403
            ), f"Unexpected access result for {cap}"
            if res.status_code == 200:
                assert res.headers.get("cache-control") == "no-store"
                body = res.json()
                assert not body["stale"], "Published data violates freshness threshold"
                if cap != "health":
                    assert body["release_id"] and body["as_of"]
        assert http.get(
            base + "/api/v1/customers", headers=headers, params={"tenant": "forged"}
        ).status_code in {403, 422}
        assert (
            http.post(base + "/api/v1/claims", headers=headers, json={}).status_code
            == 405
        )
    if not any(set(i["capabilities"]) != set(paths) for i in clients):
        raise SystemExit("Include a restricted identity to exercise forbidden views")
    namespace = config["namespace"]
    if not namespace.replace("-", "").isalnum():
        raise SystemExit("Invalid namespace")
    metric_headers = (
        {"Authorization": "Bearer " + config["prometheus_token"]}
        if config.get("prometheus_token")
        else {}
    )
    queries = [
        f'omniclaim_data_dependency_up{{namespace="{namespace}"}}',
        f'omniclaim_http_requests_total{{namespace="{namespace}",service_name="omniclaim-api"}}',
    ]
    for query in queries:
        for attempt in range(20):
            result = http.get(
                prom + "/api/v1/query", params={"query": query}, headers=metric_headers
            )
            result.raise_for_status()
            series = result.json()["data"]["result"]
            if series and all(float(x["value"][1]) > 0 for x in series):
                break
            time.sleep(5)
        else:
            raise AssertionError(
                "Required application/monitor telemetry is missing or failing"
            )
print(
    json.dumps(
        {
            "live_oidc": True,
            "tenant_and_role_checks": True,
            "real_serving_views": True,
            "read_only": True,
            "freshness": True,
            "metrics_visible": True,
        }
    )
)
