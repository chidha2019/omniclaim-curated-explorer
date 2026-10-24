"""Fail closed outside local/test; all application settings use APP_ prefix."""

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Dataset = Literal["customers", "policies", "claims"]
Capability = Literal["customers", "policies", "claims", "health"]
IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class TenantPolicy(BaseModel):
    pipeline_id: str = Field(min_length=1, max_length=120)
    groups: dict[str, list[Capability]]
    roles: dict[Capability, str]

    @model_validator(mode="after")
    def roles_valid(self):
        if not self.roles or any(not IDENTIFIER.fullmatch(r) for r in self.roles.values()):
            raise ValueError("Only explicit uppercase Snowflake role identifiers are allowed")
        if any(c not in self.roles for caps in self.groups.values() for c in caps):
            raise ValueError("Every capability needs a configured database role")
        return self


class AccessPolicy(BaseModel):
    tenants: dict[str, TenantPolicy]

    @model_validator(mode="after")
    def isolation(self):
        owners: dict[str, str] = {}
        if not self.tenants:
            raise ValueError("Configure at least one tenant")
        for tenant, policy in self.tenants.items():
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", tenant):
                raise ValueError("Invalid tenant identifier")
            for role in policy.roles.values():
                if role in owners and owners[role] != tenant:
                    raise ValueError("A Snowflake role cannot be shared across application tenants")
                owners[role] = tenant
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")
    environment: Literal["local", "test", "staging", "production"] = "local"
    data_mode: Literal["fixtures", "snowflake"] = "fixtures"
    version: str = "dev"
    policy_file: Path = Path("../config/access-policy.example.json")
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    oidc_issuer: str = ""
    oidc_jwks_url: str = ""
    oidc_audience: str = ""
    oidc_client_id: str = ""
    oidc_scope: str = "openid profile omniclaim.read"
    required_scope: str = "omniclaim.read"
    cursor_key_file: Path | None = None
    audit_key_file: Path | None = None
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_database: str = "OMNICLAIM"
    snowflake_warehouse: str = "OMNICLAIM_APP_WH"
    snowflake_key_file: Path | None = None
    snowflake_key_password_file: Path | None = None
    query_timeout_seconds: int = Field(default=30, ge=1, le=30)
    max_concurrent_queries: int = Field(default=4, ge=1, le=16)
    queue_timeout_seconds: float = Field(default=2, gt=0, le=5)
    freshness_seconds: int = Field(default=7200, ge=60)
    telemetry_enabled: bool = False
    otlp_endpoint: str = "https://otel-collector:4318"
    otlp_ca_file: Path | None = None
    otlp_cert_file: Path | None = None
    otlp_key_file: Path | None = None
    trace_sample_ratio: float = Field(default=0.1, ge=0, le=1)

    @property
    def demo(self) -> bool:
        return self.environment in {"local", "test"} and self.data_mode == "fixtures"

    @model_validator(mode="after")
    def production_guard(self):
        for value in (self.snowflake_database, self.snowflake_warehouse):
            if not IDENTIFIER.fullmatch(value):
                raise ValueError("Invalid Snowflake identifier")
        if self.environment in {"production", "staging"}:
            if self.data_mode != "snowflake" or not self.telemetry_enabled:
                raise ValueError("Deployed environments require Snowflake and telemetry")
            if self.version == "dev" or "*" in self.allowed_hosts:
                raise ValueError("Set version and explicit allowed hosts")
            required = [
                self.cursor_key_file,
                self.audit_key_file,
                self.snowflake_key_file,
                self.otlp_ca_file,
                self.otlp_cert_file,
                self.otlp_key_file,
            ]
            if any(x is None or not x.is_file() for x in required):
                raise ValueError("Required mounted secret or TLS file is missing")
            if not all(
                [self.snowflake_account, self.snowflake_user, self.oidc_audience, self.oidc_client_id]
            ):
                raise ValueError("Configure Snowflake identity and OIDC audience/client")
            if not all(
                v.startswith("https://") for v in [self.oidc_issuer, self.oidc_jwks_url, self.otlp_endpoint]
            ):
                raise ValueError("OIDC and telemetry endpoints require HTTPS")
        if not self.demo and not all([self.oidc_issuer, self.oidc_jwks_url, self.oidc_audience]):
            raise ValueError("Real data always requires OIDC")
        return self

    def load_policy(self) -> AccessPolicy:
        policy = AccessPolicy.model_validate(json.loads(self.policy_file.read_text()))
        if self.environment in {"staging", "production"} and any(
            "health" not in entry.roles for entry in policy.tenants.values()
        ):
            raise ValueError("Every deployed tenant needs an observer role for independent monitoring")
        return policy
