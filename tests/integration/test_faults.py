"""Targeted failures: every fault before commit leaves no business mutation behind."""

import time

import psycopg
import pytest

from tests.integration.support import (
    ADMIN_URL,
    Gate,
    background,
    error_code,
    install_hook,
    post_batch,
    snapshot,
    wait_until,
    waiting_sessions,
)


def three_recipients(base):
    return [(base["B"], "10.00", "b"), (base["C"], "20.00", "c"), (base["D"], "30.00", "d")]


def assert_next_request_succeeds(clients, base, label):
    for name, client in clients.items():
        response = post_batch(client, base["A"], [(base["B"], "0.01", f"{label} via {name}")])
        assert response.status_code == 201, response.text


@pytest.mark.case("FLT001", "FLT002", "FLT003", "FLT004", "FLT005", "FLT006", "FLT008")
@pytest.mark.parametrize(
    "stage",
    ["after_validation", "after_locks", "after_payer_balance", "after_payee_balance",
     "after_balances", "after_payment_insert", "before_return"],
)
def test_fault_at_stage_rolls_back(admin, apis, base, stage):
    install_hook(admin, stage, "raise")
    before = snapshot()
    for client in apis.values():
        response = post_batch(client, base["A"], three_recipients(base))
        assert (response.status_code, error_code(response)) == (500, "internal_error")
        assert "injected" not in response.text
    assert snapshot() == before
    admin.execute("DELETE FROM test_support.hook_rules")
    assert_next_request_succeeds(apis, base, stage)


@pytest.mark.case("FLT007")
def test_database_error_on_later_row(admin, apis, base):
    admin.execute(
        """
        CREATE FUNCTION test_support.reject_boom() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.description = 'boom' THEN
                RAISE EXCEPTION USING ERRCODE = 'check_violation', MESSAGE = 'controlled failure';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER reject_boom BEFORE INSERT ON app.payments
            FOR EACH ROW EXECUTE FUNCTION test_support.reject_boom();
        """
    )
    try:
        before = snapshot()
        response = post_batch(apis["api-1"], base["A"], [(base["B"], "1.00", "fine"), (base["C"], "1.00", "boom")])
        assert (response.status_code, error_code(response)) == (500, "internal_error")
        assert snapshot() == before
    finally:
        admin.execute("DROP TRIGGER reject_boom ON app.payments; DROP FUNCTION test_support.reject_boom()")
    assert_next_request_succeeds(apis, base, "after trigger")


def api_backend_pids() -> list[int]:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT pid FROM pg_stat_activity WHERE usename = 'payments_api'"
            " AND wait_event_type = 'Lock' AND wait_event = 'advisory'"
        ).fetchall()
    return [pid for (pid,) in rows]


@pytest.mark.case("FLT010")
def test_connection_lost_before_commit(admin, apis, base):
    before = snapshot()
    with Gate(admin, "before_return") as gate:
        pending = background(post_batch, apis["api-1"], base["A"], three_recipients(base))
        gate.wait_for(1)
        (pid,) = api_backend_pids()
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
    response = pending.result(timeout=30)
    assert (response.status_code, error_code(response)) == (503, "temporarily_unavailable")
    assert snapshot() == before
    assert_next_request_succeeds(apis, base, "after connection loss")


@pytest.mark.case("FLT013")
def test_lock_wait_timeout(admin, apis, base):
    before = snapshot()
    with psycopg.connect(ADMIN_URL) as blocker:
        blocker.execute("SELECT 1 FROM app.firms WHERE id = %s FOR UPDATE", (base["B"].id,))
        started = time.monotonic()
        response = post_batch(apis["api-2"], base["A"], [(base["B"], "1.00", "blocked")])
        elapsed = time.monotonic() - started
        blocker.rollback()
    assert (response.status_code, error_code(response)) == (503, "temporarily_unavailable")
    assert 1.5 < elapsed < 6
    assert snapshot() == before
    assert_next_request_succeeds(apis, base, "after lock timeout")


@pytest.mark.case("FLT014")
@pytest.mark.slow
def test_statement_timeout(admin, apis, base):
    install_hook(admin, "after_locks", "sleep", arg=6)
    before = snapshot()
    started = time.monotonic()
    response = post_batch(apis["api-3"], base["A"], [(base["B"], "1.00", "slow")])
    elapsed = time.monotonic() - started
    assert (response.status_code, error_code(response)) == (503, "temporarily_unavailable")
    assert 3.5 < elapsed < 6
    assert snapshot() == before
    admin.execute("DELETE FROM test_support.hook_rules")
    assert_next_request_succeeds(apis, base, "after statement timeout")


@pytest.mark.case("FLT017")
def test_pooled_connections_survive_failures(admin, apis, base):
    install_hook(admin, "after_locks", "raise")
    for client in apis.values():
        for _ in range(12):  # more than the pool's minimum size, so failures touch many connections
            assert post_batch(client, base["A"], [(base["B"], "0.01", "fails")]).status_code == 500
    admin.execute("DELETE FROM test_support.hook_rules")
    for i in range(6):
        assert_next_request_succeeds(apis, base, f"reuse {i}")


def all_ready(apis) -> bool:
    return all(client.get("/health/ready").status_code == 200 for client in apis.values())


@pytest.mark.case("OPS010")
@pytest.mark.slow
def test_database_unavailable_before_acquisition(admin, apis, base, mode):
    admin.execute("ALTER ROLE payments_api NOLOGIN")
    try:
        admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = 'payments_api'")
        before = snapshot()
        entries = [(base["B"], "5.00", "while down")]
        for client in apis.values():
            response = post_batch(client, base["A"], entries)
            assert (response.status_code, error_code(response)) == (503, "temporarily_unavailable")
            assert client.get("/health/ready").status_code == 503
        assert snapshot() == before
    finally:
        admin.execute("ALTER ROLE payments_api LOGIN")
    wait_until(lambda: all_ready(apis), timeout=60, interval=0.5)
    repeat = post_batch(apis["api-1"], base["A"], entries)
    assert (repeat.status_code, repeat.json()["inserted_count"]) == (201, 1)
    assert_next_request_succeeds(apis, base, "after outage")


@pytest.mark.case("OPS010")
def test_database_unavailable_during_request(admin, apis, base, mode):
    entries = [(base["B"], "5.00", "interrupted")]
    with Gate(admin, "after_locks") as gate:
        pending = background(post_batch, apis["api-1"], base["A"], entries)
        gate.wait_for(1)
        admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = 'payments_api'")
    response = pending.result(timeout=30)
    assert (response.status_code, error_code(response)) == (503, "temporarily_unavailable")
    assert snapshot().payments == []
    wait_until(lambda: all_ready(apis), timeout=30, interval=0.5)
    repeat = post_batch(apis["api-1"], base["A"], entries)
    assert (repeat.status_code, repeat.json()["inserted_count"]) == (201, 1)
