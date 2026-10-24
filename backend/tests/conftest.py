from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.fixtures import FixtureRepository
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings():
    return Settings(
        environment="test", policy_file=ROOT / "config/access-policy.example.json", trace_sample_ratio=1
    )


@pytest.fixture
def repo():
    return FixtureRepository()


@pytest.fixture
def client(settings, repo):
    with TestClient(create_app(settings, repository=repo)) as client:
        yield client


@pytest.fixture
def headers():
    return {"Authorization": "Bearer local-demo"}
