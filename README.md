# OmniClaim Curated Explorer

A complete read-only React + TypeScript and FastAPI application for published Snowflake insurance data. The existing S3 → Snowflake-managed Iceberg Bronze/Silver/Gold pipelines remain in their own repository. This package does not replace or redeploy those pipelines.

The application includes customer browsing, policy aggregates, claim performance, data freshness/quality, OIDC Authorization Code + PKCE, JWT verification, tenant/role enforcement, signed release-aware pagination, OpenAPI, tests, container builds, Kubernetes Helm deployment, Jenkins promotion/rollback, OpenTelemetry, Prometheus alerts and a Grafana dashboard.

**Production deployment requires your environment configuration and passing live staging gates.** This ZIP contains no Snowflake credentials, identity-provider registration, running infrastructure or invented production verification. See `VALIDATION.md` for exactly what was executed.

## Start locally

Requirements: Python 3.12, Node 24, npm, and Make. Linux/macOS shell examples:

```bash
make install
make dev
```

Open the Vite URL printed by the command, normally http://localhost:5173. Select **Explore demo workspace**. All local records are synthetic and clearly labeled. On Windows, use WSL2 or Docker Desktop. Local mode cannot be deployed through the production chart.

Alternatively:

```bash
docker compose up --build
```

Open http://localhost:8080. This is an isolated local fixture environment, not a production compose deployment.

## Validate

```bash
make test
make build
make check-assets   # requires Helm 3
.venv/bin/python tools/export_openapi.py --check
cd frontend
npx playwright install chromium   # install browser OS dependencies on the CI image
npm run test:e2e
```

`tools/verify_observability.py` runs a real collector integration test with ephemeral mTLS and a local OTLP sink. Set `OTELCOL_BINARY` to otelcol-contrib 0.163.2. Jenkins runs this gate on the Linux CI agent.

## Deploy

Follow `docs/DEPLOYMENT.md`. The supported deployment is Kubernetes with a maintained Gateway API controller, an existing HTTPS Gateway, Prometheus Operator and an existing OTLP backend. The application chart deploys only its API, web server, independent data monitor, collector, policies and monitoring resources.

Jenkins builds once, scans and signs immutable image digests, deploys staging, verifies real OIDC/Snowflake access and metrics, then promotes the same digests after release approval. Application deployment never runs pipeline transformations or grants itself database administration privileges.

## Files to begin with

| Purpose | Location |
| --- | --- |
| Four React workspaces | `frontend/src/App.tsx` |
| API and authorization | `backend/app/main.py`, `backend/app/auth.py` |
| Parameterized queries and grain | `backend/app/sql.py`, `contracts/data-contract.json` |
| API contract | `contracts/openapi.json` |
| Tenant/group/role configuration | `config/access-policy.example.json` |
| Application-specific serving views | `tools/render_serving_sql.py` |
| Deployment and pipeline | `deploy/chart/`, `Jenkinsfile`, `ci/` |
| Telemetry, alerts and dashboard | `observability/` |
| Repository graph evidence | `knowledge/assets.json`, `docs/KNOWLEDGE-GRAPH.md` |
| Operational recovery | `docs/runbooks/` |

Policy rows are aggregates, not individual policy records. Claim rows contain performance fields, not a complete claim case file. Monetary amounts remain decimal strings and are never combined across currencies.
