import secrets
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi import Query as QueryParams
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import Authenticator, Principal, principal, require
from .config import Settings
from .cursors import Cursors
from .datasets import DATASETS
from .errors import AppError
from .middleware import RequestTelemetry
from .models import BrowserBatch, Claim, Customer, HealthStatus, Page, PolicyMetric, Query
from .telemetry import Telemetry


class BrowserBudget:
    def __init__(self):
        self.clients = OrderedDict()
        self.lock = threading.Lock()

    def take(self, key, count):
        with self.lock:
            now = time.monotonic()
            start, used = self.clients.pop(key, (now, 0))
            if now - start > 60:
                start, used = now, 0
            if used + count > 120:
                raise AppError(429, "telemetry_rate_limit", "Telemetry budget exceeded.")
            self.clients[key] = (start, used + count)
            if len(self.clients) > 4096:
                self.clients.popitem(last=False)


def create_app(settings: Settings | None = None, repository=None, telemetry=None):
    s = settings or Settings()
    policy = s.load_policy()

    @asynccontextmanager
    async def lifespan(app):
        app.state.telemetry = telemetry or Telemetry(s)
        app.state.auth = Authenticator(s, policy)
        app.state.audit_key = s.audit_key_file.read_bytes() if s.audit_key_file else secrets.token_bytes(32)
        cursor_key = s.cursor_key_file.read_bytes() if s.cursor_key_file else secrets.token_bytes(32)
        if len(app.state.audit_key) < 32:
            raise ValueError("Audit key needs 32 bytes")
        app.state.cursors = Cursors(cursor_key)
        if repository is not None:
            app.state.repo = repository
        elif s.demo:
            from .fixtures import FixtureRepository

            app.state.repo = FixtureRepository()
        else:
            from .repository import SnowflakeRepository

            app.state.repo = SnowflakeRepository(s, app.state.telemetry)
        app.state.budget = BrowserBudget()
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            app.state.repo.close()
            app.state.telemetry.close()

    app = FastAPI(
        title="OmniClaim Curated Explorer",
        version="1.0.0",
        lifespan=lifespan,
        description="Read-only access to published insurance data. Decimal amounts are JSON strings. Currency and grain are preserved.",
        docs_url="/docs" if s.demo else None,
        redoc_url=None,
        openapi_url="/openapi.json" if s.demo else None,
    )
    app.add_middleware(RequestTelemetry, state=app.state)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.allowed_hosts)

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else {}
        if exc.status in {429, 503}:
            headers["Retry-After"] = "5"
        return JSONResponse(
            {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=exc.status,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        # Do not echo tokens, search text, or rejected body values back into error telemetry.
        return JSONResponse(
            {
                "code": "invalid_request",
                "message": "Check the request parameters.",
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=422,
        )

    @app.get("/health/live", include_in_schema=False)
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", include_in_schema=False)
    def ready(request: Request):
        return JSONResponse(
            {"status": "ready" if request.app.state.ready else "starting"},
            status_code=200 if request.app.state.ready else 503,
        )

    @app.get("/api/v1/config", operation_id="getRuntimeConfig", tags=["Configuration"])
    def runtime_config():
        return dict(
            demo=s.demo,
            version=s.version,
            authority=s.oidc_issuer,
            client_id=s.oidc_client_id,
            scope=s.oidc_scope,
            telemetry_sample_ratio=s.trace_sample_ratio,
            freshness_seconds=s.freshness_seconds,
        )

    @app.get("/api/v1/me", operation_id="getCurrentUser", tags=["Identity"])
    def me(user: Principal = Depends(principal)):
        return {"tenant": user.tenant, "capabilities": sorted(user.capabilities)}

    def page(request, user, dataset, query):
        require(user, dataset)
        entry = policy.tenants[user.tenant]
        release, offset = request.app.state.cursors.read(user.tenant, dataset, query)
        rows, current, as_of = request.app.state.repo.page(
            dataset, user.tenant, entry.pipeline_id, entry.roles[dataset], query, release, offset
        )
        more = len(rows) > query.limit
        if more and offset + query.limit > 10000:
            raise AppError(422, "browse_limit", "Narrow your filters to browse fewer than 10,000 records.")
        cursor = (
            request.app.state.cursors.issue(user.tenant, dataset, query, current, offset + query.limit)
            if more
            else None
        )
        return {
            "items": [DATASETS[dataset].model.model_validate(r) for r in rows[: query.limit]],
            "next_cursor": cursor,
            "release_id": current,
            "as_of": as_of,
            "stale": (datetime.now(UTC) - as_of).total_seconds() > s.freshness_seconds,
        }

    @app.get(
        "/api/v1/customers", response_model=Page[Customer], operation_id="listCustomers", tags=["Customers"]
    )
    def customers(
        request: Request, query: Annotated[Query, QueryParams()], user: Principal = Depends(principal)
    ):
        return page(request, user, "customers", query)

    @app.get(
        "/api/v1/policies",
        response_model=Page[PolicyMetric],
        operation_id="listPolicyMetrics",
        tags=["Policies"],
    )
    def policies(
        request: Request, query: Annotated[Query, QueryParams()], user: Principal = Depends(principal)
    ):
        return page(request, user, "policies", query)

    @app.get("/api/v1/claims", response_model=Page[Claim], operation_id="listClaims", tags=["Claims"])
    def claims(
        request: Request, query: Annotated[Query, QueryParams()], user: Principal = Depends(principal)
    ):
        return page(request, user, "claims", query)

    @app.get(
        "/api/v1/data-health", response_model=HealthStatus, operation_id="getDataHealth", tags=["Data health"]
    )
    def health(request: Request, user: Principal = Depends(principal)):
        require(user, "health")
        entry = policy.tenants[user.tenant]
        row = request.app.state.repo.health(user.tenant, entry.pipeline_id, entry.roles["health"])
        as_of = row["active_as_of"]
        row["stale"] = as_of is None or (datetime.now(UTC) - as_of).total_seconds() > s.freshness_seconds
        return row

    @app.post(
        "/api/v1/telemetry/browser", status_code=202, operation_id="ingestBrowserSpans", tags=["Telemetry"]
    )
    def browser_spans(batch: BrowserBatch, request: Request, user: Principal = Depends(principal)):
        request.app.state.budget.take((user.tenant, request.state.actor), max(1, len(batch.spans)))
        request.app.state.telemetry.browser(batch.spans)
        return Response(status_code=202)

    return app
