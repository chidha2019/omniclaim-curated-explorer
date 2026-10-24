import gzip
import http.server
import ipaddress
import ssl
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.models import BrowserSpan
from app.telemetry import Telemetry


def test_real_sdk_mtls_transport_all_signals(settings, tmp_path, monkeypatch):
    """Verify actual Python/browser-span exporters with a strict TLS sink, without mocking HTTP."""
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ephemeral-test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False
        )
        .sign(key, hashes.SHA256())
    )
    certfile = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    received = {}

    class Sink(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            data = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            received.setdefault(self.path, []).append(data)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)
    context.load_verify_locations(certfile)
    context.verify_mode = ssl.CERT_REQUIRED
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"https://127.0.0.1:{server.server_port}"
    tls_settings = settings.model_copy(
        update={
            "telemetry_enabled": True,
            "otlp_endpoint": endpoint,
            "otlp_ca_file": certfile,
            "otlp_cert_file": certfile,
            "otlp_key_file": keyfile,
        }
    )
    telemetry = Telemetry(tls_settings)
    try:
        with (
            httpx.Client(
                verify=ssl.create_default_context(cafile=str(certfile)), trust_env=False, timeout=2
            ) as client,
            pytest.raises(httpx.HTTPError),
        ):
            client.post(endpoint + "/v1/traces", content=b"")
        with telemetry.tracer.start_as_current_span("test-server"):
            telemetry.audit(route="/api/v1/customers", status=200, customer_name="never-export-this")
        telemetry.requests.add(1, {"route": "/api/v1/customers", "method": "GET", "status_class": "2xx"})
        telemetry.browser(
            [
                BrowserSpan(
                    name="GET /api/v1/customers",
                    trace_id="1" * 32,
                    span_id="2" * 16,
                    start_ns=time.time_ns(),
                    duration_ns=1000000,
                    error=False,
                )
            ]
        )
        telemetry.provider.force_flush()
        telemetry.browser_processor.force_flush()
        telemetry.meter_provider.force_flush()
        telemetry.logger_provider.force_flush()
        assert {"/v1/traces", "/v1/metrics", "/v1/logs"} <= received.keys()
        assert len(received["/v1/traces"]) >= 2
        assert all(
            b"never-export-this" not in payload for batches in received.values() for payload in batches
        )
    finally:
        telemetry.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
