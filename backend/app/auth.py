import hashlib
import hmac
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .config import AccessPolicy, Settings
from .errors import AppError

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    tenant: str
    subject: str
    capabilities: frozenset[str]


class Authenticator:
    def __init__(self, settings: Settings, policy: AccessPolicy):
        self.settings, self.policy = settings, policy
        self.keys = (
            None
            if settings.demo
            else PyJWKClient(settings.oidc_jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)
        )

    def authenticate(self, token: str) -> Principal:
        if self.settings.demo:
            if token != "local-demo":  # noqa: S105 - fixtures-only marker; denied in deployed environments
                raise AppError(401, "invalid_token", "Sign in to continue.")
            tenant, entry = next(iter(self.policy.tenants.items()))
            return Principal(tenant, "local-demo-user", frozenset(entry.roles))
        if len(token) > 16384:
            raise AppError(401, "invalid_token", "Invalid access token.")
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.settings.oidc_audience,
                issuer=self.settings.oidc_issuer,
                leeway=30,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWKClientConnectionError as exc:
            raise AppError(503, "identity_unavailable", "Identity service is unavailable.") from exc
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise AppError(401, "invalid_token", "Sign in again to continue.") from exc
        return self.authorize(claims)

    def authorize(self, claims: dict) -> Principal:
        tenant, groups, subject = claims.get("tenant_id"), claims.get("groups", []), claims.get("sub")
        scope = claims.get("scope", claims.get("scp", ""))
        scopes = scope.split() if isinstance(scope, str) else scope
        if not isinstance(scopes, list) or self.settings.required_scope not in scopes:
            raise AppError(403, "insufficient_scope", "Application access is not assigned.")
        if not isinstance(tenant, str) or tenant not in self.policy.tenants:
            raise AppError(403, "unknown_tenant", "Tenant access is not assigned.")
        if not isinstance(subject, str) or not subject or not isinstance(groups, list) or len(groups) > 200:
            raise AppError(403, "invalid_identity", "Identity claims are invalid.")
        if any(not isinstance(g, str) for g in groups):
            raise AppError(403, "invalid_identity", "Identity groups are invalid.")
        mapping = self.policy.tenants[tenant].groups
        caps = frozenset(c for g in groups for c in mapping.get(g, []))
        if not caps:
            raise AppError(403, "no_access", "Application access is not assigned.")
        return Principal(tenant, subject, caps)


def principal(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(401, "authentication_required", "Sign in to continue.")
    user = request.app.state.auth.authenticate(credentials.credentials)
    request.state.tenant = user.tenant
    request.state.actor = hmac.new(
        request.app.state.audit_key, user.subject.encode(), hashlib.sha256
    ).hexdigest()[:24]
    return user


def require(user: Principal, capability: str):
    if capability not in user.capabilities:
        raise AppError(403, "forbidden", "You do not have access to this workspace.")
