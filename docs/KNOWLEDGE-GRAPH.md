# Crawl this repository into the Context Hub

`knowledge/assets.json` is a declared evidence map, not a prebuilt graph database. Crawl it together with Python/TypeScript ASTs, OpenAPI, SQL generation/query modules, tests, Helm and Jenkins. The data object names are stable cross-repository join keys; replace the logical database alias with the actual environment catalog in your catalog resolver.

Recommended node types: Repository, Component, Endpoint, Schema, DataView, DataProduct, Test, Pipeline, Workload, TelemetrySignal, Alert, Runbook, Team and BusinessMetric. Useful edges: CALLS, QUERIES, READS, DESCRIBES, TESTS, DEPLOYS, EMITS, ALERTS_ON, RESOLVED_BY and OWNED_BY.

Every extracted edge needs evidence: repository ID, commit SHA, file path, symbol or JSON pointer, extractor name/version and confidence/evidence status. Preserve exact source line ranges from your crawler; do not store invented line numbers from this manifest. The dynamic dataset router has explicit mappings in `backend/app/datasets.py`; do not infer a direct SQL dependency solely from component filenames.

| Persona | Questions supported by repository evidence |
| --- | --- |
| Application engineering | Which route/model/query must change when a serving column changes? |
| QA | Which tests cover authorization, publication rollover, currency grain and error recovery? |
| Data engineering | Which application contract consumes each published Gold product? |
| Business analysis | What are the grain, currency handling and timing semantics of a displayed metric? |
| DevOps / SRE | Which image, rollout, signal, alert and runbook belong to this service? |
| Security / governance | Where are tenant restrictions enforced, and which role may read contact data? |

Link the app views to the lakehouse object's existing Gold → Silver → Bronze → source lineage. Do not duplicate the full lakehouse source code here. Individual policy-detail data is absent from this release and must not be hallucinated by agents from the aggregate endpoint name.

Static evidence does not prove a test passed or a workload is running. Ingest CI JUnit/coverage/SBOM/signature/commit evidence and runtime telemetry separately with timestamps and environment identities. The validation report describes local execution only. Revoke stale edges when code or deployments change. Keep customer rows, credentials and test identity secrets outside the graph.
