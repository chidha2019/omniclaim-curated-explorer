# Primary implementation references

Verified during implementation on 2026-10-24. Dependency versions are pinned in the lockfiles and image digests.

- FastAPI OpenAPI and model behavior: https://fastapi.tiangolo.com/features/
- Snowflake Python connector: https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-api
- Snowflake CURRENT_ROLE: https://docs.snowflake.com/en/sql-reference/functions/current_role
- OIDC client implementation: https://github.com/authts/oidc-client-ts
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/instrumentation/
- Collector configuration: https://opentelemetry.io/docs/collector/configuration/
- Pinned collector release: https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.163.2
- Gateway API timeouts: https://gateway-api.sigs.k8s.io/guides/user-guides/http-timeouts/
- Community ingress-nginx retirement: https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/
- Kubernetes probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Jenkins pipeline: https://www.jenkins.io/doc/book/pipeline/syntax/

Existing application data sources were inspected from the supplied OmniClaim pipeline package's `sql/bootstrap/serving.sql` and control-table contract. No live Snowflake account was queried during creation.
