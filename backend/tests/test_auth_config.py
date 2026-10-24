import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.auth import Authenticator
from app.config import AccessPolicy, Settings
from app.errors import AppError


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def auth(settings, key):
    config = settings.model_copy(
        update={
            "data_mode": "snowflake",
            "oidc_issuer": "https://issuer.example",
            "oidc_audience": "api",
            "oidc_jwks_url": "https://issuer.example/keys",
        }
    )
    a = Authenticator(config, settings.load_policy())
    a.keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
    return a


def claims(**kw):
    return dict(
        iss="https://issuer.example",
        aud="api",
        sub="user1",
        iat=int(time.time()),
        exp=int(time.time()) + 300,
        tenant_id="demo",
        groups=["omniclaim-analyst"],
        scope="omniclaim.read",
        **kw,
    )


def test_valid_signature_and_capabilities(auth, key):
    p = auth.authenticate(jwt.encode(claims(), key, algorithm="RS256"))
    assert p.tenant == "demo" and p.capabilities == {"claims", "policies"}


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "other"},
        {"iss": "https://attacker.example"},
        {"exp": 0},
        {"iat": int(time.time()) + 3600},
        {"sub": None},
    ],
)
def test_claim_validation(auth, key, change):
    c = claims()
    c.update(change)
    with pytest.raises(AppError) as e:
        auth.authenticate(jwt.encode(c, key, algorithm="RS256"))
    assert e.value.status == 401


def test_wrong_key(auth):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AppError):
        auth.authenticate(jwt.encode(claims(), other, algorithm="RS256"))


def test_algorithm_confusion_denied(auth):
    with pytest.raises(AppError):
        auth.authenticate(jwt.encode(claims(), "x" * 32, algorithm="HS256"))


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": "other"},
        {"groups": ["administrators"]},
        {"groups": "omniclaim-support"},
        {"scope": ""},
        {"groups": [{}]},
    ],
)
def test_missing_entitlement(auth, change):
    c = claims()
    c.update(change)
    with pytest.raises(AppError) as e:
        auth.authorize(c)
    assert e.value.status == 403


def test_cross_tenant_role_reuse_rejected(settings):
    value = settings.load_policy().model_dump()
    value["tenants"]["other"] = value["tenants"]["demo"]
    with pytest.raises(ValidationError):
        AccessPolicy.model_validate(value)


@pytest.mark.parametrize("env", ["production", "staging"])
def test_deployed_mode_rejects_fixture_bypass(env):
    with pytest.raises(ValidationError):
        Settings(environment=env, data_mode="fixtures")


def test_live_data_requires_oidc():
    with pytest.raises(ValidationError):
        Settings(environment="local", data_mode="snowflake")


@pytest.mark.parametrize("name", ["BAD;DROP DATABASE X", "lowercase", "A.B", 'A"B'])
def test_unsafe_identifier_rejected(name):
    with pytest.raises(ValidationError):
        Settings(snowflake_database=name)
