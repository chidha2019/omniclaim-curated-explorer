# Deployment guide

## Platform prerequisites

Provision separate `omniclaim-staging` and `omniclaim-production` namespaces on a supported Kubernetes version with amd64 worker nodes. Install a maintained Gateway API implementation with HTTPRoute request-timeout support, Metrics Server, Prometheus Operator CRDs (including Probe and AlertmanagerConfig), kube-state-metrics, a Blackbox exporter, Grafana, durable encrypted storage and your OTLP backend. Use at least two schedulable nodes for the application replicas.

Provide a platform HTTPS Gateway with a valid certificate for the application hostname, private/corporate ingress restrictions, a 64 KiB request limit, rate limiting and sanitized access logs that exclude query strings and authorization headers. Allow routes from the application namespaces. Configure its `allowedRoutes` deliberately. The chart references its name, namespace and HTTPS listener. HTTP-to-HTTPS redirection is a platform listener policy; do not expose a second plaintext route.

Traffic inside the cluster uses HTTP between Gateway, web and API. For environments requiring encryption on every hop, enable the platform’s enforced service-mesh mTLS on these namespaces and Gateway backends before release; telemetry already uses explicit application-level mTLS.

The default CNI policy allows DNS to CoreDNS, web-to-API traffic, API/monitor-to-collector traffic, monitoring scrapes, and only configured external CIDRs on ports 443/80. Snowflake TLS/OCSP, IdP and OTLP endpoints must resolve inside those approved ranges or use your approved egress gateway. Do not substitute `0.0.0.0/0` without an environment security review. Adapt the CoreDNS selector to your cluster if necessary. Port 80 is for certificate/OCSP dependencies; business endpoints still require HTTPS.

## 1. Establish the data contract

The lakehouse pipeline must already have a successful published release. The app needs the exact existing views and columns listed in `contracts/data-contract.json`. It does not infer missing joins or create policy detail data.

Configure `config/access-policy.json` from the example. Use one tenant-specific Snowflake role for support, one for analysts and one for observers, with distinct roles between tenants. Group names are IdP group identifiers; replace the example names with the actual claims your provider issues. Set the correct upstream `pipeline_id`.

Generate reviewable SQL:

```bash
.venv/bin/python tools/render_serving_sql.py \
  --database OMNICLAIM --user OMNICLAIM_APP \
  --policy config/access-policy.json --output build/app-serving.sql
```

Review and execute the generated SQL with an approved bootstrap identity that can own the views, read the existing source views/control tables, create/grant roles and maintain `CONTROL.ROLE_TENANTS`. The wrapper view owner must retain required source privileges. Grant `USAGE` on the dedicated app warehouse to the generated roles. Verify there are no existing conflicting `ROLE_TENANTS` mappings, inherited broad roles, future grants or direct raw-table grants. Application roles must map to exactly one tenant. Use fresh role names when in doubt.

Give the service user a rotated RSA key pair. Store only the public key in Snowflake; the private key comes from your managed secrets system. Set a warehouse resource monitor, auto-suspend and capacity appropriate to measured concurrency. The key-pair service user is an application trust boundary; it can assume the configured tenant roles, so it must never be exposed to end users.

## 2. Register OIDC

Register a public SPA client using Authorization Code + PKCE; no client secret belongs in React. Register the exact callback `https://<host>/auth/callback` and logout `https://<host>/`. Enable token-endpoint CORS for the application origin. Require an API audience distinct from the SPA client ID, `omniclaim.read` scope, `tenant_id`, and string-array `groups` claims on **access tokens**. Adapt the issuer's claims mapper, not the browser, to enforce the tenant.

The browser keeps the user/access token only in memory. PKCE interaction state uses sessionStorage and is cleared by the OIDC library after callback. Page reload can require a fresh IdP redirect; there is no embedded refresh-token persistence or silent iframe flow. The server accepts only the configured issuer, audience and RS256. JWKS refresh is bounded and cached for five minutes.

Set `app.issuerOrigin` to the HTTPS origin used by discovery and token exchange. If your IdP uses multiple origins, review and extend the generated CSP explicitly; do not use a wildcard. Never supply auth tokens via query strings.

## 3. Create managed secret projections

Create these Kubernetes Secrets through your existing secrets manager/CSI/operator; do not commit their contents:

| Secret | Keys |
| --- | --- |
| `omniclaim-runtime` | `snowflake.p8` (PEM key), `cursor.key` (at least 32 random bytes), `audit.key` (separate random bytes) |
| `omniclaim-otel-client` | `tls.crt`, `tls.key`, `ca.crt` for API/monitor client authentication |
| `omniclaim-otel-server` | `tls.crt`, `tls.key`, `ca.crt`; server certificate SAN must include `explorer-collector` and its used DNS names |
| `omniclaim-observability-backend` | `OTLP_BACKEND_ENDPOINT` (HTTPS base URL), `OTLP_BACKEND_TOKEN`, `ca.crt` (trusted backend CA bundle) |
| `omniclaim-oncall` | `url` containing the approved incident webhook URL |

Client certificates require client-auth EKU; the collector certificate requires server-auth EKU. Use your enterprise CA and short-lived certificates. Mount renewal through managed secrets and roll workloads before expiry. Certificate authority/key material must never be emitted to logs. If the Snowflake key is encrypted, add its password file to the runtime secret and configure `APP_SNOWFLAKE_KEY_PASSWORD_FILE`.

The `cursor.key` must be identical across API replicas; rotating it invalidates existing cursors. `audit.key` generates pseudonymous actor IDs and has separate access/retention requirements. SDK client credentials are mounted read-only with group-readable permissions for the non-root processes.

## 4. Configure the chart and monitoring

Copy each `deploy/environments/*.example.yaml` to its environment file and replace hostname, IdP metadata, tenant mapping, Snowflake account/user/database/warehouse, Gateway, egress CIDRs and runbook URL. Examples deliberately contain non-routable documentation domains/ranges. `ci/deploy.py` refuses those placeholders. The pipeline injects tested image digests and the Git commit.

Configure Prometheus to select the supplied ServiceMonitor, Probe and PrometheusRule resources in both namespaces. Configure Alertmanager to select the supplied AlertmanagerConfig by the `release` label. Verify the Blackbox exporter can resolve/access the private HTTPS application endpoint. It checks `/api/v1/config`, which reveals public configuration only. Import `observability/grafana-dashboard.json` and select the Prometheus datasource and environment namespace.

All PromQL in the chart is namespace-scoped. An existing OTLP backend receives traces, metrics and logs over verified TLS. The collector exposes internal metrics at 8888 and application metrics at 8889 only to the monitoring namespace. Browser spans go through the authenticated API; the collector is not exposed to browsers or the public internet.

## 5. Configure Jenkins

Use a disposable Linux CI agent labeled `omniclaim-linux`, with Python 3.12, Node 24, Helm 3, kubectl, Docker Buildx, Trivy, Cosign, Prometheus promtool and Chromium + its OS dependencies for the locked Playwright version. Install the pinned otelcol-contrib 0.163.2 binary and set `OTELCOL_BINARY`. Pin the CI-agent image and those tools under your platform supply-chain policy.

Required Jenkins plugins: Pipeline, Git, Credentials Binding, JUnit, Lockable Resources, Timestamper and your KMS/workload-identity integration. Configure the `omniclaim-release-managers` submitter group. Enforce branch protection and trusted Jenkinsfile execution; PR jobs must have no production credentials or signing permissions.

Job environment: `REGISTRY_HOST`, `IMAGE_REPOSITORY`, `COSIGN_KEY_REF` (KMS/HSM reference), and `OTELCOL_BINARY`. Signing access comes from the CI workload identity. Provide these credential IDs:

- `omniclaim-registry`: registry username/password or short-lived robot token.
- `omniclaim-cosign-public-key`: verification public-key file.
- `omniclaim-staging-kubeconfig`, `omniclaim-production-kubeconfig`: namespaced deployment identities.
- `omniclaim-staging-values`, `omniclaim-production-values`: reviewed chart values files.
- `omniclaim-staging-smoke`, `omniclaim-production-smoke`: JSON Secret Files following `config/smoke.example.json`.

Smoke identities need client-credentials tokens with the same API access-token claim contract as real users. Provide two independent test tenants with published data; at least one identity must have restricted capabilities. Production uses dedicated synthetic/test tenant partitions, not broad customer access. Configure a read-only Prometheus API identity. The live smoke check cannot fall back to fixtures.

`main` builds, scans and signs the images, then deploys staging. After `PROMOTE_PRODUCTION` is selected and release approval granted, the same image digests are deployed to production. Helm atomic rollout handles workload failures; route-status or post-deployment smoke failures trigger rollback. A failed first installation removes only that new Helm release; persistent collector PVCs are retained by Kubernetes policy.

The CI deployer needs namespaced permissions for the chart's resources and Helm release Secrets. Pre-provision namespaces and platform CRDs. CI must not have cluster-admin or Snowflake bootstrap rights. Require image-signature admission enforcement in the cluster in addition to the CI Cosign verification.

## Release acceptance

A release requires all CI stages, accepted/resolved HTTPRoute conditions, real OIDC access tests, tenant/role restrictions, real serving-view reads, data freshness, visible monitor/API metrics, a successful collector integration test, healthy external probes and an on-call routing drill. Review traces/logs in the chosen backend and rotate/test certificates before the first production approval. Load-test your actual warehouse and identity provider: the included functional checks do not establish a production throughput guarantee.
