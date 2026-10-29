import json

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from app.db import map_db_error


class FakeDiag:
    def __init__(self, detail):
        self.message_detail = detail


def db_error(sqlstate, base=psycopg.DatabaseError, detail=None):
    cls = type("FakeDbError", (base,), {"sqlstate": sqlstate, "diag": FakeDiag(detail)})
    return cls("database said no")


@pytest.mark.parametrize(
    "exc, during_commit, status, code",
    [
        (db_error("TD001"), False, 422, "unknown_firm"),
        (db_error("TD002"), False, 422, "insufficient_funds"),
        (db_error("TD003"), False, 422, "numeric_overflow"),
        (db_error("TD004"), False, 409, "payment_amount_conflict"),
        (db_error("TD005"), False, 422, "validation_error"),
        (db_error("TD006"), False, 503, "temporarily_unavailable"),
        (db_error("55P03", psycopg.errors.OperationalError), False, 503, "temporarily_unavailable"),
        (db_error("57014", psycopg.errors.OperationalError), False, 503, "temporarily_unavailable"),
        (db_error("40P01", psycopg.errors.TransactionRollback), False, 503, "temporarily_unavailable"),
        (db_error("57P01", psycopg.errors.OperationalError), False, 503, "temporarily_unavailable"),
        (db_error(None, psycopg.OperationalError), False, 503, "temporarily_unavailable"),
        (db_error(None, psycopg.OperationalError), True, 503, "commit_outcome_unknown"),
        (PoolTimeout("pool exhausted"), False, 503, "temporarily_unavailable"),
        (db_error("P0001"), False, 500, "internal_error"),
        (db_error("23514", psycopg.errors.IntegrityError), False, 500, "internal_error"),
        (RuntimeError("bug"), False, 500, "internal_error"),
    ],
)
def test_map_db_error(exc, during_commit, status, code):
    error = map_db_error(exc, during_commit)
    assert (error.status, error.code) == (status, code)
    assert "database said no" not in error.message


def test_details_come_from_detail_json():
    detail = [{"index": 1, "path": "payments[1].payee_firm_uuid"}]
    error = map_db_error(db_error("TD001", detail=json.dumps(detail)), False)
    assert error.details == detail


def test_non_json_detail_is_ignored():
    assert map_db_error(db_error("TD002", detail="not json"), False).details is None
