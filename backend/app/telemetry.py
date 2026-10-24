"""Explicit allowlist of telemetry fields. Never record URLs, query text, tokens, or row values."""

import json
import logging
import sys
import time
from datetime import UTC, datetime

import requests
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanContext, SpanKind, Status, StatusCode, TraceFlags

from .config import Settings
from .errors import AppError


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "event": record.getMessage(),
        }
        event.update(getattr(record, "safe_fields", {}))
        return json.dumps(event, default=str)


class Telemetry:
    def __init__(self, s: Settings, service="omniclaim-api"):
        self.resource = Resource.create(
            {
                "service.name": service,
                "service.version": s.version,
                "deployment.environment.name": s.environment,
            }
        )
        self.provider = TracerProvider(
            resource=self.resource, sampler=ParentBased(TraceIdRatioBased(s.trace_sample_ratio))
        )
        self.browser_processor = None
        self.logger_provider = LoggerProvider(resource=self.resource)
        self.logger = logging.Logger("omniclaim.audit", level=logging.INFO)
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(JsonFormatter())
        self.logger.addHandler(stream)
        readers = []
        if s.telemetry_enabled:
            args = {"timeout": 5}
            if s.otlp_ca_file:
                args["certificate_file"] = str(s.otlp_ca_file)
            if s.otlp_cert_file:
                args["client_certificate_file"] = str(s.otlp_cert_file)
            if s.otlp_key_file:
                args["client_key_file"] = str(s.otlp_key_file)

            def options():
                session = requests.Session()
                # Internal collector mTLS must use the explicitly mounted CA, not process-wide proxy/CA overrides.
                session.trust_env = False
                return {**args, "session": session}

            base = s.otlp_endpoint.rstrip("/")
            self.provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=base + "/v1/traces", **options()),
                    max_queue_size=2048,
                    max_export_batch_size=256,
                    schedule_delay_millis=2000,
                )
            )
            self.browser_processor = BatchSpanProcessor(
                OTLPSpanExporter(endpoint=base + "/v1/traces", **options()),
                max_queue_size=1024,
                max_export_batch_size=128,
            )
            readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=base + "/v1/metrics", **options()),
                    export_interval_millis=15000,
                )
            )
            self.logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(OTLPLogExporter(endpoint=base + "/v1/logs", **options()))
            )
            self.logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=self.logger_provider))
        self.meter_provider = MeterProvider(
            resource=self.resource,
            metric_readers=readers,
            views=[
                View(
                    instrument_name="omniclaim_http_duration_seconds",
                    aggregation=ExplicitBucketHistogramAggregation(
                        [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60]
                    ),
                ),
                View(
                    instrument_name="omniclaim_query_duration_seconds",
                    aggregation=ExplicitBucketHistogramAggregation(
                        [0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60]
                    ),
                ),
            ],
        )
        self.tracer = self.provider.get_tracer("omniclaim")
        self.meter = self.meter_provider.get_meter("omniclaim")
        self.requests = self.meter.create_counter("omniclaim_http_requests")
        self.duration = self.meter.create_histogram("omniclaim_http_duration_seconds", unit="s")
        self.query_errors = self.meter.create_counter("omniclaim_query_failures")
        self.query_duration = self.meter.create_histogram("omniclaim_query_duration_seconds", unit="s")
        self.browser_rejected = self.meter.create_counter("omniclaim_browser_spans_rejected")
        self.browser_resource = Resource.create(
            {
                "service.name": "omniclaim-web",
                "service.version": s.version,
                "deployment.environment.name": s.environment,
            }
        )
        # Library logging must not accidentally emit connector SQL or HTTP headers.
        for name in ["snowflake.connector", "httpx", "httpcore", "urllib3"]:
            logging.getLogger(name).setLevel(logging.CRITICAL)

    def audit(self, **fields):
        safe = {
            k: v
            for k, v in fields.items()
            if k
            in {
                "request_id",
                "trace_id",
                "actor",
                "tenant",
                "route",
                "method",
                "status",
                "duration_ms",
                "code",
            }
        }
        self.logger.info("request_completed", extra={"safe_fields": safe, **safe})

    def browser(self, spans):
        now = time.time_ns()
        for s in spans:
            if (
                int(s.trace_id, 16) == 0
                or int(s.span_id, 16) == 0
                or not now - 600_000_000_000 <= s.start_ns <= now + 60_000_000_000
            ):
                self.browser_rejected.add(1)
                raise AppError(422, "invalid_span", "Invalid browser trace timestamp or identifier.")
        if self.browser_processor:
            for s in spans:
                ctx = SpanContext(int(s.trace_id, 16), int(s.span_id, 16), False, TraceFlags(1))
                self.browser_processor.on_end(
                    ReadableSpan(
                        name=s.name,
                        context=ctx,
                        kind=SpanKind.CLIENT,
                        resource=self.browser_resource,
                        start_time=s.start_ns,
                        end_time=s.start_ns + s.duration_ns,
                        status=Status(StatusCode.ERROR if s.error else StatusCode.OK),
                        attributes={
                            "telemetry.source": "browser_untrusted",
                            "http.route": s.name.split(" ", 1)[1],
                        },
                    )
                )

    def close(self):
        if self.browser_processor:
            self.browser_processor.shutdown()
        self.provider.shutdown()
        self.meter_provider.shutdown()
        self.logger_provider.shutdown()
        for h in self.logger.handlers:
            h.close()
