import threading
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.errors import AppError
from app.models import Query
from app.repository import SnowflakeRepository


@pytest.fixture
def repo(settings):
    r = SnowflakeRepository.__new__(SnowflakeRepository)
    r.settings = settings
    r.key = b"test"
    r.slots = threading.BoundedSemaphore(1)
    r.telemetry = SimpleNamespace(
        tracer=SimpleNamespace(start_as_current_span=lambda *a, **kw: nullcontext(Mock())),
        query_errors=Mock(),
        query_duration=Mock(),
    )
    return r


def test_role_timeout_bound_parameters_and_cleanup(repo, monkeypatch):
    cur = Mock()
    cur.description = [("VALUE",)]
    cur.fetchall.return_value = [(3,)]
    cur.sfqid = "query-id"
    cur.__enter__ = Mock(return_value=cur)
    cur.__exit__ = Mock()
    conn = Mock()
    conn.cursor.return_value = cur
    conn.__enter__ = Mock(return_value=conn)
    conn.__exit__ = Mock()
    connect = Mock(return_value=conn)
    monkeypatch.setattr("snowflake.connector.connect", connect)
    assert repo.execute("SELECT %s", (3,), "TENANT_A_ANALYST", "policies") == [{"value": 3}]
    assert connect.call_args.kwargs["role"] == "TENANT_A_ANALYST"
    assert connect.call_args.kwargs["query_timeout"] == 30
    assert cur.execute.call_args_list[0].args == ("USE SECONDARY ROLES NONE",)
    assert cur.execute.call_args_list[1].args == ("SELECT %s", (3,))
    assert cur.__exit__.called and conn.__exit__.called
    assert repo.slots.acquire(blocking=False)


def test_failure_returns_capacity(repo, monkeypatch):
    monkeypatch.setattr(
        "snowflake.connector.connect", Mock(side_effect=RuntimeError("sensitive database error"))
    )
    with pytest.raises(AppError) as e:
        repo.execute("SELECT 1", (), "TENANT_A_ANALYST", "policies")
    assert e.value.code == "data_unavailable" and "sensitive" not in e.value.message
    assert repo.slots.acquire(blocking=False)


def test_overload_does_not_open_connection(repo, monkeypatch):
    repo.settings = repo.settings.model_copy(update={"queue_timeout_seconds": 0.001})
    repo.slots.acquire()
    connect = Mock()
    monkeypatch.setattr("snowflake.connector.connect", connect)
    with pytest.raises(AppError) as e:
        repo.execute("SELECT 1", (), "TENANT_A_ANALYST", "policies")
    assert e.value.code == "query_capacity" and not connect.called


@pytest.mark.parametrize(
    "rows,code",
    [([], "not_published"), ([{"_release_id": "r", "_release_count": 2}], "pipeline_state_invalid")],
)
def test_missing_or_duplicate_publication(repo, rows, code):
    repo.execute = Mock(return_value=rows)
    with pytest.raises(AppError) as e:
        repo.page("customers", "a", "p", "ROLE", Query(), None, 0)
    assert e.value.code == code
