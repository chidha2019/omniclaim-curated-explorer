import time

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from app.telemetry import Telemetry


def test_trace_parent_and_log_redaction(settings, repo, headers, capsys):
    telemetry = Telemetry(settings)
    exporter = InMemorySpanExporter()
    telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace_id = "1234567890abcdef1234567890abcdef"
    h = {**headers, "traceparent": f"00-{trace_id}-1234567890abcdef-01"}
    with TestClient(create_app(settings, repo, telemetry)) as c:
        r = c.get("/api/v1/customers?q=secret-customer@example.com", headers=h)
        assert r.headers["x-trace-id"] == trace_id
    spans = exporter.get_finished_spans()
    assert spans[0].name == "GET /api/v1/customers"
    assert "secret-customer" not in str(spans[0].attributes)
    logs = capsys.readouterr().out
    assert "secret-customer" not in logs and "local-demo" not in logs
    assert trace_id in logs


def span():
    return dict(
        name="GET /api/v1/customers",
        trace_id="1" * 32,
        span_id="2" * 16,
        start_ns=time.time_ns(),
        duration_ns=12000000,
        error=False,
    )


def test_browser_trace_ingestion(client, headers):
    assert (
        client.post("/api/v1/telemetry/browser", headers=headers, json={"spans": [span()]}).status_code == 202
    )


@pytest.mark.parametrize(
    "change",
    [
        {"url": "https://leak.example/customer"},
        {"name": "customer private name"},
        {"trace_id": "0" * 32},
        {"start_ns": 1},
        {"duration_ns": 121000000000},
    ],
)
def test_browser_trace_allowlist(client, headers, change):
    item = span()
    item.update(change)
    assert (
        client.post("/api/v1/telemetry/browser", headers=headers, json={"spans": [item]}).status_code == 422
    )


def test_browser_trace_bounded(client, headers):
    data = {"spans": [span()] * 20}
    for _ in range(6):
        assert client.post("/api/v1/telemetry/browser", headers=headers, json=data).status_code == 202
    assert client.post("/api/v1/telemetry/browser", headers=headers, json=data).status_code == 429
