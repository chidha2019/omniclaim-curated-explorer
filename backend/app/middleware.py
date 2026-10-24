import time
import uuid

from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.datastructures import Headers
from starlette.responses import JSONResponse


class RequestTelemetry:
    def __init__(self, app, state):
        self.app, self.state = app, state

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > 65536:
                return await JSONResponse(
                    {"code": "body_too_large", "message": "Request exceeds 64 KiB."}, status_code=413
                )(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        status, started = 500, time.monotonic()
        telemetry = self.state.telemetry
        # Baggage is deliberately not propagated: it can contain PII or attacker-controlled attributes.
        carrier = {
            k: headers[k] for k in ("traceparent", "tracestate") if k in headers and len(headers[k]) < 512
        }
        with telemetry.tracer.start_as_current_span(
            "HTTP request",
            context=extract(carrier),
            kind=SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            trace_id = f"{span.get_span_context().trace_id:032x}"

            async def safe_send(message):
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                    message["headers"] = list(message.get("headers", [])) + [
                        (b"x-request-id", request_id.encode()),
                        (b"x-trace-id", trace_id.encode()),
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                await send(message)

            try:
                await self.app(scope, bounded_receive, safe_send)
            except Exception:
                await JSONResponse(
                    {
                        "code": "internal_error",
                        "message": "An unexpected error occurred.",
                        "request_id": request_id,
                    },
                    status_code=500,
                )(scope, bounded_receive, safe_send)
            finally:
                route = getattr(scope.get("route"), "path", "unmatched")
                method = scope["method"] if scope["method"] in {"GET", "POST", "OPTIONS"} else "OTHER"
                span.update_name(f"{method} {route}")
                span.set_attribute("http.route", route)
                span.set_attribute("http.request.method", method)
                span.set_attribute("http.response.status_code", status)
                if status >= 500:
                    span.set_status(Status(StatusCode.ERROR, "server_error"))
                elapsed = time.monotonic() - started
                labels = {"route": route, "method": method, "status_class": f"{status // 100}xx"}
                telemetry.requests.add(1, labels)
                telemetry.duration.record(elapsed, labels)
                if route.startswith("/api/") and route != "/api/v1/config":
                    telemetry.audit(
                        request_id=request_id,
                        trace_id=trace_id,
                        route=route,
                        method=method,
                        status=status,
                        duration_ms=round(elapsed * 1000, 2),
                        actor=scope["state"].get("actor"),
                        tenant=scope["state"].get("tenant"),
                    )
