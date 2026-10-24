import time

import pytest
import sqlglot

from app.cursors import Cursors
from app.errors import AppError
from app.models import Query
from app.sql import health_sql, page_sql


@pytest.mark.parametrize("dataset", ["customers", "policies", "claims"])
def test_sql_parameterization(settings, dataset):
    q = Query(q="x'); DROP TABLE CLAIMS; --", currency="USD")
    sql, params = page_sql(settings, dataset, "tenant-a", "pipeline", q, None, 0)
    assert q.q not in sql and q.q in params
    assert params[:2] == ("tenant-a", "pipeline") and sql.count("%s") == len(params)
    parsed = sqlglot.parse_one(sql.replace("%s", "'bound'"), read="snowflake")
    assert parsed.key == "select"
    assert "_RELEASE_COUNT" in sql


def test_health_sql_is_select(settings):
    assert sqlglot.parse_one(health_sql(settings).replace("%s", "'bound'"), read="snowflake").key == "select"


def test_cursor_tampering_and_context():
    c = Cursors(b"1" * 32)
    q = Query()
    value = c.issue("a", "customers", q, "release", 25)
    assert c.read("a", "customers", Query(cursor=value)) == ("release", 25)
    for tenant, kind, token in [
        ("b", "customers", value),
        ("a", "claims", value),
        ("a", "customers", value[:-2] + "xx"),
    ]:
        with pytest.raises(AppError):
            c.read(tenant, kind, Query(cursor=token))


def test_expired_cursor(monkeypatch):
    c = Cursors(b"1" * 32)
    q = Query()
    v = c.issue("a", "customers", q, "r", 25)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 901)
    with pytest.raises(AppError):
        c.read("a", "customers", Query(cursor=v))


def test_bad_sort_never_enters_sql(settings):
    with pytest.raises(AppError):
        page_sql(settings, "customers", "a", "p", Query(sort="SLEEP(100)"), None, 0)
