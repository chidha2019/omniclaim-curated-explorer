"""Independent Kubernetes CronJob: Snowflake connectivity, publication freshness and quality health."""

import sys
import time

from .config import Settings
from .repository import SnowflakeRepository
from .telemetry import Telemetry


def main():
    s = Settings()
    t = Telemetry(s, "omniclaim-monitor")
    repo = SnowflakeRepository(s, t)
    up = t.meter.create_gauge("omniclaim_data_dependency_up")
    last = t.meter.create_gauge("omniclaim_monitor_last_success_timestamp_seconds")
    published = t.meter.create_gauge("omniclaim_published_as_of_timestamp_seconds")
    quality = t.meter.create_gauge("omniclaim_quality_failures")
    attempt = t.meter.create_gauge("omniclaim_pipeline_last_attempt_failed")
    failed = False
    try:
        for tenant, entry in s.load_policy().tenants.items():
            if "health" not in entry.roles:
                raise ValueError("Every deployed tenant requires a health role for monitoring")
            labels = {"tenant": tenant}
            try:
                state = repo.health(tenant, entry.pipeline_id, entry.roles["health"])
                up.set(1, labels)
                attempt.set(int(state["last_attempt_status"] == "FAILED"), labels)
                last.set(time.time(), labels)
                ts = state["active_as_of"]
                published.set(ts.timestamp() if ts else 0, labels)
                quality.set(sum(c["failures"] for c in state["checks"]), labels)
            except Exception:
                up.set(0, labels)
                failed = True
                t.logger.error("dependency_probe_failed", extra={"tenant": tenant})
        t.meter_provider.force_flush(timeout_millis=10000)
    finally:
        repo.close()
        t.close()
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
