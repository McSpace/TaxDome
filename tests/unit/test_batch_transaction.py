"""Transaction ownership in Database._run_batch, with a scripted fake connection."""

import asyncio

import psycopg
import pytest
from psycopg import pq

from app.config import Settings
from app.db import Database
from app.errors import ApiError


class LostConnection(psycopg.OperationalError):
    sqlstate = None


class FakeCursor:
    async def fetchone(self):
        return ({"inserted_count": 1},)


class FakeConnection:
    """Records statements and fails on the first one that starts with `fail_on`."""

    def __init__(self, fail_on: str | None):
        self.fail_on = fail_on
        self.statements: list[str] = []
        self.closed = False
        self.broken = False
        self.in_transaction = False

    @property
    def info(self):
        status = pq.TransactionStatus.INTRANS if self.in_transaction else pq.TransactionStatus.IDLE
        return type("Info", (), {"transaction_status": status})()

    async def execute(self, query, params=None):
        self.statements.append(query)
        if query.startswith("BEGIN"):
            self.in_transaction = True
        if self.fail_on and query.startswith(self.fail_on):
            self.broken = True
            raise LostConnection("connection lost")
        if query in ("COMMIT", "ROLLBACK"):
            self.in_transaction = False
        return FakeCursor()


def run(conn: FakeConnection):
    database = Database(Settings(instance_id="t", database_url="postgresql://unused"))
    return asyncio.run(database._run_batch(conn, "uuid", "[]"))


def test_connection_lost_during_commit_is_unknown_outcome():
    conn = FakeConnection(fail_on="COMMIT")
    with pytest.raises(ApiError) as info:
        run(conn)
    assert info.value.code == "commit_outcome_unknown"
    assert "ROLLBACK" not in conn.statements


def test_connection_lost_during_function_call_is_rolled_back():
    conn = FakeConnection(fail_on="SELECT app.process_payment_batch")
    with pytest.raises(ApiError) as info:
        run(conn)
    assert info.value.code == "temporarily_unavailable"
    assert "COMMIT" not in conn.statements


def test_success_commits_once():
    conn = FakeConnection(fail_on=None)
    assert run(conn) == {"inserted_count": 1}
    assert conn.statements[0].startswith("BEGIN ISOLATION LEVEL READ COMMITTED")
    assert conn.statements[-1] == "COMMIT"
