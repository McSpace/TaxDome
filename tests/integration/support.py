"""Fixtures data, database helpers and fault hooks for integration tests.

Everything here runs in the test-runner container against the disposable test
database, using superuser credentials that the API instances never receive.
"""

import itertools
import json
import os
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace

import psycopg

ADMIN_URL = os.environ.get("ADMIN_DATABASE_URL", "")
API_DB_URL = os.environ.get("API_DATABASE_URL", "")
MAX_CENTS = 2_147_483_647


@dataclass(frozen=True)
class Firm:
    alias: str
    id: int
    uuid: str
    cents: int
    name: str


BASE_FIXTURE = (
    Firm("A", 30, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 10000, "Alder Accounting"),
    Firm("B", 10, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", 2000, "Birch Bookkeeping"),
    Firm("C", 20, "cccccccc-cccc-4ccc-8ccc-cccccccccccc", 0, "Cedar Tax"),
    Firm("D", 40, "dddddddd-dddd-4ddd-8ddd-dddddddddddd", 5000, "Dogwood CPA"),
)
ABSENT_UUID = "ffffffff-ffff-4fff-8fff-ffffffffffff"

SAMPLE_FIXTURE = (
    Firm("Pinecrest", 1, "3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41", 5000000, "Pinecrest CPA Group"),
    Firm("Lopez", 2, "8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10", 50000, "Lopez Bookkeeping"),
    Firm("Nair", 3, "e5f18b3c-2a9d-4c07-8e6b-1d4a7f9c3b25", 200000, "Nair Tax Services"),
)


def with_balances(firms: Iterable[Firm], **cents: int) -> tuple[Firm, ...]:
    """Return a copy of a fixture with some aliases' opening balances replaced."""
    return tuple(replace(f, cents=cents[f.alias]) if f.alias in cents else f for f in firms)


def admin_connect() -> psycopg.Connection:
    return psycopg.connect(ADMIN_URL, autocommit=True)


def reset_db(admin: psycopg.Connection, firms: Iterable[Firm]) -> None:
    admin.execute("TRUNCATE app.payments, app.firms RESTART IDENTITY")
    with admin.cursor() as cur:
        cur.executemany(
            "INSERT INTO app.firms (id, name, balance_cents, uuid) VALUES (%s, %s, %s, %s)",
            [(f.id, f.name, f.cents, f.uuid) for f in firms],
        )


@dataclass(frozen=True)
class Snapshot:
    balances: dict[int, int]
    payments: list[tuple[int, int, int, int, str]]

    @property
    def total(self) -> int:
        return sum(self.balances.values())

    def rows_without_ids(self) -> list[tuple[int, int, int, str]]:
        return [row[1:] for row in self.payments]


def snapshot() -> Snapshot:
    """Read firms and payments in one consistent read-only snapshot."""
    with psycopg.connect(ADMIN_URL) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        balances = dict(conn.execute("SELECT id, balance_cents FROM app.firms").fetchall())
        payments = conn.execute(
            "SELECT id, payer_firm_id, payee_firm_id, amount_cents, description"
            " FROM app.payments ORDER BY id"
        ).fetchall()
    return Snapshot(balances, payments)


def entries_json(entries: Iterable[tuple[str, int, str]]) -> str:
    """Internal function input from (payee_uuid, amount_cents, description) tuples."""
    return json.dumps(
        [{"payee_firm_uuid": p, "amount_cents": c, "description": d} for p, c, d in entries]
    )


def call_function_as_api(
    payer_uuid: str, entries: Iterable[tuple[str, int, str]], session_setup: str | None = None
) -> dict:
    """Invoke the batch function exactly as the API role does, in one transaction."""
    with psycopg.connect(API_DB_URL) as conn:
        if session_setup:
            conn.execute(session_setup)
        (result,) = conn.execute(
            "SELECT app.process_payment_batch(%s, %s::jsonb)",
            (payer_uuid, entries_json(entries)),
        ).fetchone()
    return result


HOOK_SETUP = """
CREATE SCHEMA IF NOT EXISTS test_support;
CREATE TABLE IF NOT EXISTS test_support.hook_rules (
    id bigserial PRIMARY KEY,
    stage text NOT NULL,
    payer_id integer,
    action text NOT NULL CHECK (action IN ('raise', 'block', 'sleep')),
    arg bigint
);
GRANT USAGE ON SCHEMA test_support TO payments_owner;
GRANT SELECT ON test_support.hook_rules TO payments_owner;
CREATE OR REPLACE FUNCTION app.test_hook(stage text, payer_id integer)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $hook$
DECLARE
    rule record;
BEGIN
    FOR rule IN
        SELECT h.action, h.arg FROM test_support.hook_rules h
        WHERE h.stage = test_hook.stage
          AND (h.payer_id IS NULL OR h.payer_id = test_hook.payer_id)
        ORDER BY h.id
    LOOP
        IF rule.action = 'raise' THEN
            RAISE EXCEPTION 'injected test fault at %', stage;
        ELSIF rule.action = 'block' THEN
            -- Shared, so every blocked request proceeds together once the gate opens.
            PERFORM pg_advisory_xact_lock_shared(rule.arg);
        ELSIF rule.action = 'sleep' THEN
            PERFORM pg_sleep(rule.arg);
        END IF;
    END LOOP;
END
$hook$;
"""


def install_hook(
    admin: psycopg.Connection,
    stage: str,
    action: str,
    payer_id: int | None = None,
    arg: int | None = None,
) -> None:
    """Add a fault/pause rule; the test database's hook function evaluates rules at each stage."""
    admin.execute(HOOK_SETUP)
    admin.execute(
        "INSERT INTO test_support.hook_rules (stage, payer_id, action, arg) VALUES (%s, %s, %s, %s)",
        (stage, payer_id, action, arg),
    )


def clear_hooks(admin: psycopg.Connection) -> None:
    admin.execute(HOOK_SETUP)
    admin.execute("DELETE FROM test_support.hook_rules")


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f"condition not met within {timeout}s")
        time.sleep(interval)


BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://nginx:8080")
BATCH_PATH = "/payments/batch"
JSON_HEADERS = {"Content-Type": "application/json"}


def _uuid(firm: "Firm | str") -> str:
    return firm.uuid if isinstance(firm, Firm) else firm


def batch_body(payer: "Firm | str", entries: Iterable[tuple["Firm | str", str, str]]) -> dict:
    return {
        "payer_firm_uuid": _uuid(payer),
        "payments": [
            {"amount": amount, "payee_firm_uuid": _uuid(payee), "description": description}
            for payee, amount, description in entries
        ],
    }


def post_batch(client, payer, entries):
    """POST a batch built from (payee, amount string, description) tuples."""
    return client.post(BATCH_PATH, json=batch_body(payer, entries))


def post_raw(client, content: bytes, content_type: str | None = "application/json"):
    headers = {"Content-Type": content_type} if content_type is not None else {}
    return client.post(BATCH_PATH, content=content, headers=headers)


def error_code(response) -> str:
    return response.json()["error"]["code"]


API_URLS = {
    "api-1": "http://api-1:8000",
    "api-2": "http://api-2:8000",
    "api-3": "http://api-3:8000",
}


def installed_mode(url: str = ADMIN_URL) -> str | None:
    """Mode from the exact function signature's configuration, read as the fixture superuser."""
    with psycopg.connect(url) as conn:
        row = conn.execute(
            "SELECT cfg FROM pg_catalog.pg_proc p, unnest(p.proconfig) cfg"
            " WHERE p.oid = to_regprocedure('app.process_payment_batch(text,jsonb)')"
            " AND cfg LIKE 'app.payment_idempotency=%'"
        ).fetchone()
    return row[0].split("=", 1)[1] if row else None


def preflight(expected_mode: str) -> list[str]:
    """Compare the expected mode with the database, every API instance directly, and Nginx."""
    import httpx

    problems = []
    db_mode = installed_mode()
    if db_mode != expected_mode:
        problems.append(f"database function mode is {db_mode!r}, expected {expected_mode!r}")
    targets = [(name, url) for name, url in API_URLS.items()] + [("nginx", BASE_URL)]
    for name, url in targets:
        try:
            ready = httpx.get(f"{url}/health/ready", timeout=5)
            diag = httpx.get(f"{url}/diagnostics", timeout=5)
        except httpx.HTTPError as exc:
            problems.append(f"{name}: unreachable ({exc.__class__.__name__})")
            continue
        if ready.status_code != 200 or diag.status_code != 200:
            problems.append(f"{name}: not ready (ready={ready.status_code}, diagnostics={diag.status_code})")
            continue
        info = diag.json()
        if info.get("idempotency_mode") != expected_mode:
            problems.append(f"{name}: reports mode {info.get('idempotency_mode')!r}, expected {expected_mode!r}")
        expected_ids = set(API_URLS) if name == "nginx" else {name}
        if info.get("instance_id") not in expected_ids:
            problems.append(f"{name}: reports instance {info.get('instance_id')!r}")
    return problems


def expected_rows(payer: Firm, entries) -> list[tuple[int, int, int, str]]:
    """Rows that a fully accepted batch of (payee Firm, amount string, description) inserts."""
    from app.request_parsing import parse_amount

    return [(payer.id, payee.id, parse_amount(amount), desc) for payee, amount, desc in entries]


def assert_committed(before: Snapshot, after: Snapshot, rows: list[tuple[int, int, int, str]]) -> None:
    """Exactly `rows` were appended and balances moved by exactly their amounts."""
    assert after.rows_without_ids()[len(before.payments):] == rows
    assert after.payments[: len(before.payments)] == before.payments
    expected = dict(before.balances)
    for payer_id, payee_id, cents, _ in rows:
        expected[payer_id] -= cents
        expected[payee_id] += cents
    assert after.balances == expected
    assert all(cents >= 0 for cents in after.balances.values())
    assert after.total == before.total


def assert_unchanged(before: Snapshot, after: Snapshot) -> None:
    assert after == before


def assert_ledger(opening: Iterable[Firm], after: Snapshot) -> None:
    """Every balance equals its opening balance plus committed incoming minus outgoing."""
    expected = {f.id: f.cents for f in opening}
    for _, payer_id, payee_id, cents, _ in after.payments:
        expected[payer_id] -= cents
        expected[payee_id] += cents
    assert after.balances == expected
    assert all(cents >= 0 for cents in after.balances.values())


def waiting_sessions(event: str) -> int:
    """API-role sessions blocked on a lock: 'advisory' (test gate) or 'row' (firm row lock)."""
    events = ("transactionid", "tuple") if event == "row" else (event,)
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        (count,) = conn.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE usename = 'payments_api'"
            " AND wait_event_type = 'Lock' AND wait_event = ANY(%s)",
            (list(events),),
        ).fetchone()
    return count


_gate_keys = itertools.count(9_000_001)


class Gate:
    """Pause requests at a function stage until released (exclusive advisory lock held here)."""

    def __init__(self, admin: psycopg.Connection, stage: str, payer_id: int | None = None) -> None:
        self.key = next(_gate_keys)
        self.holder = psycopg.connect(ADMIN_URL, autocommit=True)
        self.holder.execute("SELECT pg_advisory_lock(%s)", (self.key,))
        install_hook(admin, stage, "block", payer_id, self.key)

    def wait_for(self, count: int, timeout: float = 10.0) -> None:
        wait_until(lambda: waiting_sessions("advisory") >= count, timeout)

    def release(self) -> None:
        if not self.holder.closed:
            self.holder.execute("SELECT pg_advisory_unlock(%s)", (self.key,))
            self.holder.close()

    def __enter__(self) -> "Gate":
        return self

    def __exit__(self, *exc) -> None:
        self.release()


_executor = ThreadPoolExecutor(max_workers=64)


def background(fn: Callable, *args) -> Future:
    return _executor.submit(fn, *args)


def run_parallel(calls: list[Callable]) -> list:
    futures = [_executor.submit(call) for call in calls]
    return [f.result(timeout=60) for f in futures]
