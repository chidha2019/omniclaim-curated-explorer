# Observability contract

| Signal | Source and destination | Privacy and operating rules |
| --- | --- | --- |
| Browser traces | OTel JS → authenticated `/api/v1/telemetry/browser` → server OTel exporter → collector | Only four route names, trace/span IDs, duration and status are accepted; no URL/query/body/user attributes. Max 20 spans/batch and 120 spans per actor/minute/pod. Browser spans are marked untrusted. |
| API traces | Manual OTel server spans and W3C propagation → collector | Route template, method, status; no query strings, headers or customer records. Parent-based sampling; root ratio defaults to 10%. |
| Query traces | Child `snowflake.select` span | Dataset and Snowflake query ID, never SQL text or parameters. `QUERY_TAG` links service version and trace ID in Snowflake history. |
| API metrics | OTel meter → collector → Prometheus / OTLP backend | Request count/status, duration histogram, query duration/failures; bounded labels. No per-user, query-ID or customer metrics. |
| Audit logs | Structured JSON stdout and OTLP logs | Every API request except config; request ID, trace ID, HMAC actor ID, tenant, route, status and duration. No raw subject or token. |
| Freshness/quality | Independent five-minute CronJob | Dependency availability, source AS_OF timestamp, latest attempt failure, quality failures and last successful monitor timestamp. Does not depend on browser traffic. |
| Platform | Prometheus Operator / Blackbox / kube-state-metrics | API/web replicas, external HTTPS reachability/certificate age, collector scrape health and export queue. |

Metric names and SLO definitions are in `observability/slo.yaml`. Alerts are in `observability/alerts.yaml`; the chart inserts the namespace and runbook location. Import the Grafana dashboard into the existing monitoring organization. Application logs are exported by the SDK; configure your cluster log agent to avoid double-ingesting the same API audit events. Web-server stdout logs exclude query strings; collect those with your existing cluster log agent if required.

## Data minimization

`transform/privacy` uses an attribute allowlist for all three signals and restricts log bodies to known event names. Incoming browser data is schema-validated and authenticated before queuing. Browser trace/span IDs can be supplied by an authorized user and are never treated as authoritative audit evidence. The server-generated request ID and verified token/role decision anchor an investigation.

The exporter does not capture exceptions with their potentially sensitive SQL/error messages. Investigators use the request/trace/query IDs with restricted Snowflake query history and identity audit tooling. Secure that backend because warehouse query history itself can contain SQL bind information. Never attach customer screen captures or browser storage-state files to CI artifacts.

## Reliability and limits

The collector verifies client certificates, uses memory limits, batching, retry and a persistent queue for OTLP backend exports. Prometheus scraping is separate from backend OTLP export. The queue retains already accepted telemetry across restarts, but SDK memory queues and collector capacity are finite; telemetry loss is possible during sustained outages. Collector downtime does not block data browsing. Missing-telemetry and collector-down alerts are evaluated by the independent Prometheus deployment.

A single collector is intentionally used so the pull exporter does not double-count cumulative SDK metrics across gateway replicas. To use an existing HA collector fleet, adopt the organization's metrics transport/deduplication design and revalidate alerts. Merely increasing this StatefulSet's replica count is unsupported.

Retention is enforced by your backend, not by this application: a starting policy is 30 days for sampled traces/operational metrics and 90 days for pseudonymous audit logs, adjusted to enterprise retention requirements. There is no claim that those periods have been configured remotely by this ZIP.

## Test and operational checks

`tools/verify_observability.py` generates ephemeral certificates and tests the pinned collector against a temporary local HTTPS OTLP sink. It asserts rejection without a client certificate, all three signal exports, attribute/body redaction and Prometheus metric names. It must pass on the Linux CI agent. `tools/live_smoke.py` then verifies actual staged API/monitor metrics in Prometheus. Vendor-specific trace/log retrieval and incident delivery are first-deployment acceptance checks with your chosen backend.

Set the collector's CA/SAN and both ends' TLS secrets correctly. Keep an independent enterprise certificate monitor on the client and collector certificates; the included external TLS expiry alert covers the HTTPS Gateway certificate. Rotation does not require application code changes, but rolling clients/collector after new secret material ensures connections and trust stores use it.

The API counter measures requests that entered the application. Gateway/network failures and Uvicorn admission rejections are covered by the external probe and your existing Gateway counters; use the latter for a complete user-perceived availability SLI.
