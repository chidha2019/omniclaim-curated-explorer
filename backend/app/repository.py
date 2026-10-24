import json
import threading
import time
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .config import Settings
from .errors import AppError
from .sql import health_sql, page_sql


class SnowflakeRepository:
    """Bounded per-query sessions, always role-specific and always closed; no cross-tenant session reuse."""

    def __init__(self, settings: Settings, telemetry):
        self.settings, self.telemetry = settings, telemetry
        self.slots = threading.BoundedSemaphore(settings.max_concurrent_queries)
        password = (
            settings.snowflake_key_password_file.read_bytes().strip()
            if settings.snowflake_key_password_file
            else None
        )
        key = load_pem_private_key(Path(settings.snowflake_key_file).read_bytes(), password=password)
        self.key = key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())

    def execute(self, sql: str, params: tuple, role: str, dataset: str):
        if not self.slots.acquire(timeout=self.settings.queue_timeout_seconds):
            raise AppError(503, "query_capacity", "The service is busy. Try again shortly.")
        started = time.monotonic()
        s = self.settings
        try:
            with self.telemetry.tracer.start_as_current_span(
                "snowflake.select", record_exception=False, set_status_on_exception=False
            ) as span:
                span.set_attribute("db.system.name", "snowflake")
                span.set_attribute("app.dataset", dataset)
                ctx = trace.get_current_span().get_span_context()
                tag = json.dumps(
                    {
                        "app": "omniclaim-explorer",
                        "version": s.version,
                        "trace_id": f"{ctx.trace_id:032x}",
                        "dataset": dataset,
                    }
                )
                try:
                    with snowflake.connector.connect(
                        account=s.snowflake_account,
                        user=s.snowflake_user,
                        private_key=self.key,
                        authenticator="SNOWFLAKE_JWT",
                        role=role,
                        database=s.snowflake_database,
                        warehouse=s.snowflake_warehouse,
                        login_timeout=10,
                        request_timeout=15,
                        connect_timeout=5,
                        retry_timeout=10,
                        query_timeout=s.query_timeout_seconds,
                        client_session_keep_alive=False,
                        logout_total_timeout_seconds=2,
                        logout_request_timeout_seconds=2,
                        client_out_of_band_telemetry_enabled=False,
                        log_query_text=False,
                        log_query_parameters=False,
                        session_parameters={
                            "QUERY_TAG": tag,
                            "STATEMENT_TIMEOUT_IN_SECONDS": s.query_timeout_seconds,
                            "STATEMENT_QUEUED_TIMEOUT_IN_SECONDS": 5,
                            "TIMEZONE": "UTC",
                        },
                    ) as conn:
                        with conn.cursor() as cur:
                            # Defense in depth: use no granted secondary role for this session.
                            cur.execute("USE SECONDARY ROLES NONE")
                            cur.execute(sql, params, timeout=s.query_timeout_seconds)
                            span.set_attribute("db.query.id", cur.sfqid or "unknown")
                            columns = [c[0].lower() for c in cur.description]
                            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, "query_failed"))
                    self.telemetry.query_errors.add(1, {"dataset": dataset})
                    # Connector error strings can contain SQL, hostnames or data; do not export them.
                    raise AppError(
                        503, "data_unavailable", "Curated data is temporarily unavailable."
                    ) from exc
        finally:
            self.telemetry.query_duration.record(time.monotonic() - started, {"dataset": dataset})
            self.slots.release()

    def page(self, dataset, tenant, pipeline, role, query, release, offset):
        sql, params = page_sql(self.settings, dataset, tenant, pipeline, query, release, offset)
        rows = self.execute(sql, params, role, dataset)
        if not rows or not rows[0]["_release_id"]:
            raise AppError(503, "not_published", "No curated release has been published yet.")
        if rows[0]["_release_count"] != 1:
            raise AppError(503, "pipeline_state_invalid", "A unique publication is not available.")
        current, as_of = rows[0]["_release_id"], rows[0]["_as_of"]
        if release and release != current:
            raise AppError(
                409, "publication_changed", "A new data release is available. Refresh to restart browsing."
            )
        return [r for r in rows if r.get("_present")], current, as_of

    def health(self, tenant, pipeline, role):
        rows = self.execute(health_sql(self.settings), (tenant, tenant, pipeline), role, "health")
        if len(rows) != 1:
            raise AppError(503, "pipeline_state_invalid", "A unique pipeline state is not available.")
        row = rows[0]
        if isinstance(row["checks"], str):
            row["checks"] = json.loads(row["checks"])
        return row

    def close(self):
        pass
