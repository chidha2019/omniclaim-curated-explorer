"""Generate reviewable bootstrap SQL. Does not connect or apply changes."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import AccessPolicy, IDENTIFIER

parser = argparse.ArgumentParser()
parser.add_argument("--database", required=True)
parser.add_argument("--user", required=True)
parser.add_argument("--policy", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
a = parser.parse_args()
if not all(IDENTIFIER.fullmatch(v) for v in [a.database, a.user]):
    raise SystemExit("Use uppercase unquoted identifiers")
policy = AccessPolicy.model_validate_json(a.policy.read_text())
db = a.database
sql = [
    "-- Apply once using your approved bootstrap identity. Runtime/CI deployment identities must not have DDL privileges.",
    "-- Prerequisite: pipeline serving views exist. Review existing grants on each role before applying.",
]
sql.append(f"""CREATE OR REPLACE SECURE VIEW {db}.SERVING.APP_RELEASE COPY GRANTS AS
SELECT p.PIPELINE_ID,p.TENANT_ID,p.ACTIVE_RELEASE_ID,p.ACTIVE_AS_OF,p.PUBLISHED_AT
FROM {db}.CONTROL.PIPELINE_STATE p
WHERE EXISTS (SELECT 1 FROM {db}.CONTROL.ROLE_TENANTS e WHERE e.ROLE_NAME=CURRENT_ROLE() AND e.TENANT_ID=p.TENANT_ID);""")
for app, source in [
    ("CUSTOMERS", "CUSTOMER_360"),
    ("POLICIES", "POLICY_METRICS"),
    ("CLAIMS", "LOSS_METRICS"),
]:
    sql.append(f"""CREATE OR REPLACE SECURE VIEW {db}.SERVING.APP_{app} COPY GRANTS AS
SELECT v.*, p.PIPELINE_ID, p.ACTIVE_RELEASE_ID AS RELEASE_ID
FROM {db}.SERVING.{source} v JOIN {db}.CONTROL.PIPELINE_STATE p
ON v.TENANT_ID=p.TENANT_ID AND v.AS_OF=p.ACTIVE_AS_OF;""")
for tenant, entry in policy.tenants.items():
    for role in sorted(set(entry.roles.values())):
        # Names and tenants validated by Pydantic; all business-query values remain bound parameters.
        sql.extend(
            [
                f"CREATE ROLE IF NOT EXISTS {role};",
                f"GRANT USAGE ON DATABASE {db} TO ROLE {role};",
                f"GRANT USAGE ON SCHEMA {db}.SERVING TO ROLE {role};",
                f"GRANT SELECT ON VIEW {db}.SERVING.APP_RELEASE TO ROLE {role};",
                f"GRANT ROLE {role} TO USER {a.user};",
                f"INSERT INTO {db}.CONTROL.ROLE_TENANTS (ROLE_NAME,TENANT_ID) SELECT '{role}','{tenant}' WHERE NOT EXISTS (SELECT 1 FROM {db}.CONTROL.ROLE_TENANTS WHERE ROLE_NAME='{role}' AND TENANT_ID='{tenant}');",
            ]
        )
        for capability, bound in entry.roles.items():
            if bound != role:
                continue
            views = (
                ["PIPELINE_STATUS", "QUALITY_STATUS", "RUN_STATUS"]
                if capability == "health"
                else ["APP_" + capability.upper()]
            )
            for view in views:
                sql.append(f"GRANT SELECT ON VIEW {db}.SERVING.{view} TO ROLE {role};")
sql.append(
    "-- Grant USAGE on the dedicated application warehouse to these roles separately. No raw-table grants."
)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text("\n\n".join(sql) + "\n")
