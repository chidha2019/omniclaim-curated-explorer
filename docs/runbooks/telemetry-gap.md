# Missing telemetry, queue pressure or certificate expiry

1. Check the independent Prometheus scrape, collector pod/PVC, service DNS and network policies. App request health and telemetry delivery are separate signals.
2. Inspect collector exporter failure/queue metrics and storage capacity. Verify backend availability/token and server CA trust. Do not enable payload debug exporters on customer traffic.
3. Check API/monitor client certificates and collector server SAN, expiry and CA chain. Rotate through the secrets manager and roll workloads before expiry.
4. Restore export connectivity; the persistent queue drains automatically. SDK telemetry lost before collector acceptance cannot be recovered. Record the gap rather than asserting complete audit coverage.
5. Verify API metrics, monitor heartbeat, a trace and redacted log in the backend, plus the on-call receiver. Gateway expiry alerts concern the external TLS certificate; enterprise certificate inventory must also watch the internal mTLS certificates.
