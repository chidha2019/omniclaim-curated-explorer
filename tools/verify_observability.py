"""Exercise real OTLP mTLS, collector privacy rules, all three signals and Prometheus export locally.
Requires OTELCOL_BINARY pointing to the pinned otelcol-contrib binary. Generates only ephemeral test TLS.
"""

import argparse
import gzip
import http.server
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.telemetry import Telemetry


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    binary = os.environ["OTELCOL_BINARY"]
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    with tempfile.TemporaryDirectory(prefix="omniclaim-observability-") as tmp:
        d = Path(tmp)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ephemeral-test-ca")])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None), critical=True
            )
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    ]
                ),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        (d / "ca.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (d / "tls.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (d / "tls.key").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        (d / "tls.key").chmod(0o600)
        received = {}
        lock = threading.Lock()

        class Sink(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                data = self.rfile.read(int(self.headers["Content-Length"]))
                if self.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                with lock:
                    received.setdefault(self.path, []).append(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Sink)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(d / "tls.crt", d / "tls.key")
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        ingest, metrics, internal, health = port(), port(), port(), port()
        config = (
            (ROOT / "observability/collector.yaml")
            .read_text()
            .replace("/backend-tls/ca.crt", str(d / "ca.crt"))
            .replace("/tls/", str(d) + "/")
            .replace("/var/lib/otelcol/storage", str(d / "storage"))
        )
        for old, new in [
            (4318, ingest),
            (8889, metrics),
            (8888, internal),
            (13133, health),
        ]:
            config = config.replace(f":{old}", f":{new}").replace(
                f"port: {old}", f"port: {new}"
            )
        (d / "config.yaml").write_text(config)
        env = {
            **os.environ,
            "OTLP_BACKEND_ENDPOINT": f"https://127.0.0.1:{server.server_port}",
            "OTLP_BACKEND_TOKEN": "ephemeral-test-token",
        }
        subprocess.run(
            [binary, "validate", "--config=" + str(d / "config.yaml")],
            env=env,
            check=True,
            capture_output=True,
        )
        if args.validate_only:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            print(
                json.dumps(
                    {"collector_config_valid": True, "runtime_export_tested": False}
                )
            )
            return
        log = (d / "collector.log").open("w+")
        process = subprocess.Popen(
            [binary, "--config=" + str(d / "config.yaml")],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            with httpx.Client(trust_env=False, timeout=2) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read()[-2000:])
                    try:
                        if client.get(f"http://127.0.0.1:{health}/").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("collector did not become healthy")
                # A caller without a client certificate must fail the TLS handshake.
                try:
                    with httpx.Client(
                        verify=ssl.create_default_context(cafile=str(d / "ca.crt")),
                        trust_env=False,
                        timeout=2,
                    ) as unauthorized:
                        unauthorized.post(
                            f"https://127.0.0.1:{ingest}/v1/traces", content=b""
                        )
                    raise AssertionError("collector accepted a client without mTLS")
                except httpx.HTTPError:
                    pass
                settings = Settings(
                    environment="test",
                    telemetry_enabled=True,
                    trace_sample_ratio=1,
                    policy_file=ROOT / "config/access-policy.example.json",
                    otlp_endpoint=f"https://127.0.0.1:{ingest}",
                    otlp_ca_file=d / "ca.crt",
                    otlp_cert_file=d / "tls.crt",
                    otlp_key_file=d / "tls.key",
                )
                t = Telemetry(settings)
                with t.tracer.start_as_current_span("validation") as span:
                    span.set_attribute("http.route", "/api/v1/customers")
                    span.set_attribute(
                        "customer.email", "must-not-export@example.invalid"
                    )
                t.requests.add(
                    1,
                    {
                        "route": "/api/v1/customers",
                        "method": "GET",
                        "status_class": "2xx",
                        "customer.name": "must-not-export",
                    },
                )
                t.duration.record(
                    0.15,
                    {
                        "route": "/api/v1/customers",
                        "method": "GET",
                        "status_class": "2xx",
                    },
                )
                t.logger.info(
                    "must-not-export", extra={"private_field": "must-not-export"}
                )
                t.provider.force_flush()
                t.meter_provider.force_flush()
                t.logger_provider.force_flush()
                for _ in range(150):
                    with lock:
                        ready = all(
                            received.get("/v1/" + k)
                            for k in ["traces", "metrics", "logs"]
                        )
                    if ready:
                        break
                    time.sleep(0.1)
                assert ready, "all three OTLP signals must reach the backend"
                for signal, batches in received.items():
                    assert all(b"must-not-export" not in b for b in batches), (
                        f"privacy failure: {signal}"
                    )
                text = client.get(f"http://127.0.0.1:{metrics}/metrics").text
                assert "omniclaim_http_requests_total" in text
                assert "omniclaim_http_duration_seconds_bucket" in text
                assert "customer_name" not in text
                t.close()
                print(
                    json.dumps(
                        {
                            "mtls_enforced": True,
                            "traces": True,
                            "metrics": True,
                            "logs": True,
                            "privacy_allowlist": True,
                            "prometheus_names": True,
                        }
                    )
                )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            server.shutdown()
            server.server_close()
            log.close()


if __name__ == "__main__":
    main()
