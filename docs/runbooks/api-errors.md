# API error or latency incident

1. Confirm environment, affected route and external probe; check available API/web replicas and Gateway route conditions.
2. Use the response `x-request-id` / `x-trace-id` to find the server audit record and trace. Never request customer tokens or full search URLs in a ticket.
3. If Snowflake spans dominate latency, inspect bounded concurrency, warehouse resume/queue time and the query ID in restricted query history. Check the independent dependency monitor.
4. For a new regression, review the tested commit/digest and `helm history explorer -n <namespace>`. Roll back the application to the last successful revision using the approved release process. Pipeline publication state must not be changed to roll back an application.
5. Confirm external HTTPS, an authorized API read, p95 latency, metrics and error rate recovery. Attach identifiers and dates, not row payloads.
