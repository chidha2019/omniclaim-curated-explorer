# Verification report

Verified on 2026-10-24. This report concerns the source package; no production deployment is claimed.

| Check | Result |
| --- | --- |
| Backend tests | **71 passed**, 91.87% line coverage |
| React tests | **9 passed** |
| TypeScript and Vite production build | Passed |
| Python lint/format and frontend formatting | Passed |
| Generated OpenAPI contract drift | Passed |
| Helm rendering and security assertions | Passed for staging and production examples |
| Prometheus rules | 13 rules parse; 2 behavior scenarios / 4 timing assertions pass |
| Real OTel SDK transport | Traces, browser spans, metrics and logs exported over verified mTLS to a temporary HTTPS sink; missing client certificate rejected |
| OTel Collector 0.163.2 native configuration validation | Passed |
| Dependency audits | No known Python vulnerabilities; npm reported zero vulnerabilities |

Evidence is included under `validation/`. The TLS test uses generated ephemeral test certificates and actual HTTP exporters, not mocked HTTP. Temporary private keys are not packaged.

## Remaining deployment gates

- Playwright tests are implemented and mandatory in Jenkins, but were not executed here: the managed preview runs in a separate environment without the Python application runtime. React interaction tests ran in jsdom; they do not establish browser rendering fidelity.
- The full collector integration test is implemented and mandatory in Jenkins. Native configuration validation passed, but running the collector in this environment failed while initializing its own process metrics (`process does not exist`). Python SDK mTLS transport was independently tested successfully. Collector transformation/export runtime and persistent-queue behavior still require the Linux CI environment.
- No live Snowflake account, corporate IdP, registry credentials, Kubernetes cluster or Jenkins controller was provided. Real SQL/view-grant compatibility, API access tokens, cluster admission/rollout, image scans/signing and incident delivery must pass the supplied live gates.
- Docker is unavailable locally; Docker image builds were not executed. Base images are referenced by resolved immutable registry digests, and CI scans the final images before deployment.
- Functional tests do not establish throughput, multi-AZ resilience or a 99.9% availability outcome. Verify capacity and platform failure behavior in your environment.

Known pinned-library deprecation warnings in tests concern the Starlette HTTPX test client and the OTel SDK logging handler. They did not fail tests; update them through the locked-dependency upgrade workflow and rerun the full suite.

No production secrets, customer CSV records, node_modules, virtual environment, container image, fake live verification or preconfigured external deployment is included.
