# Stale publication or quality failure

The displayed AS_OF is the source cutoff. A recent publish time does not make old source data fresh.

1. Inspect publication cutoff, latest attempted run, quality checks and the upstream pipeline's run/audit identifiers.
2. Separate ingestion delay, source contract rejection, Silver/Gold quality failure and failed publication. The previous successful release deliberately remains visible.
3. Reconcile totals at their declared grains and currencies. Do not sum policy premium across a coverage fan-out or treat days-to-last-payment as closure time.
4. Fix/reprocess the immutable source batch through the existing lakehouse pipeline. Do not modify the Gold data from the application.
5. Verify a new release, freshness gauge and quality checks. Existing browsing cursors should return 409 and restart on that release.
