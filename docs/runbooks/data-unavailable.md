# Curated data unavailable

A 503 can indicate no published release, database connectivity failure, capacity exhaustion or invalid pipeline state. Inspect the stable API error code first.

1. Confirm OIDC succeeds and the application role/tenant mapping is expected.
2. Check Snowflake account/network access, key validity, warehouse availability/resource monitor, role grants and secure view schemas.
3. Confirm exactly one publication state for the configured tenant/pipeline. Check the existing lakehouse runbook for upstream failures.
4. Never grant a broad owner or pipeline role to make a read succeed. Restore the specific view/warehouse grants or intended publication contract.
5. Retry the independent monitor and an authorized read. A schema mismatch needs a reviewed application/pipeline contract change and staging tests.
