"""Stored-function behavior, privileges and initialization against real PostgreSQL."""

import json
import os
import subprocess
import sys
import uuid

import psycopg
import pytest
from psycopg import errors

from app.migrate import MigrationError, migrate
from tests.integration.support import (
    ABSENT_UUID,
    ADMIN_URL,
    API_DB_URL,
    SAMPLE_FIXTURE,
    call_function_as_api,
    installed_mode,
    reset_db,
    snapshot,
    with_balances,
    BASE_FIXTURE,
)

OPPOSITE = {"on": "off", "off": "on"}


def detail(exc: psycopg.Error) -> list:
    return json.loads(exc.diag.message_detail)


@pytest.mark.case("BAS005")
def test_sample_function_result(admin):
    reset_db(admin, SAMPLE_FIXTURE)
    pinecrest, lopez, nair = SAMPLE_FIXTURE
    result = call_function_as_api(
        pinecrest.uuid,
        [
            (nair.uuid, 625000, "Overflow returns, August 2026"),
            (nair.uuid, 580050, "Amended returns, August 2026"),
            (lopez.uuid, 120075, "Bookkeeping cleanup, 3 clients"),
        ],
    )
    assert result["inserted_count"] == 3
    assert result["skipped_count"] == 0
    assert result["gross_outgoing_cents"] == 1325125
    after = snapshot()
    assert after.balances == {1: 3674875, 2: 170075, 3: 1405050}
    assert after.total == 5250000
    assert after.rows_without_ids() == [
        (1, 3, 625000, "Overflow returns, August 2026"),
        (1, 3, 580050, "Amended returns, August 2026"),
        (1, 2, 120075, "Bookkeeping cleanup, 3 clients"),
    ]


@pytest.mark.case("BAS008", "BAT001")
def test_insufficient_funds_rolls_back(base):
    before = snapshot()
    with pytest.raises(psycopg.Error) as info:
        call_function_as_api(
            base["A"].uuid, [(base["B"].uuid, 6000, "one"), (base["C"].uuid, 6000, "two")]
        )
    assert info.value.sqlstate == "TD002"
    assert snapshot() == before


@pytest.mark.case("FRM001", "FRM002", "FRM003")
def test_unknown_firm(base):
    before = snapshot()
    with pytest.raises(psycopg.Error) as info:
        call_function_as_api(
            base["A"].uuid,
            [(base["B"].uuid, 100, "x"), (ABSENT_UUID, 100, "y"), (base["C"].uuid, 100, "z")],
        )
    assert info.value.sqlstate == "TD001"
    assert detail(info.value) == [{"index": 1, "path": "payments[1].payee_firm_uuid"}]

    with pytest.raises(psycopg.Error) as info:
        call_function_as_api(ABSENT_UUID, [(base["B"].uuid, 100, "x")])
    assert info.value.sqlstate == "TD001"
    assert detail(info.value) == [{"index": None, "path": "payer_firm_uuid"}]
    assert snapshot() == before


@pytest.mark.case("BAT008")
def test_self_payment_gross_rule(base):
    a, b = base["A"], base["B"]
    with pytest.raises(psycopg.Error) as info:
        call_function_as_api(a.uuid, [(a.uuid, 10000, "self"), (b.uuid, 10000, "external")])
    assert info.value.sqlstate == "TD002"

    result = call_function_as_api(a.uuid, [(a.uuid, 10000, "self only")])
    assert result["inserted_count"] == 1
    after = snapshot()
    assert after.balances[a.id] == 10000
    assert after.rows_without_ids() == [(a.id, a.id, 10000, "self only")]


@pytest.mark.case("PAY001", "PAY002", "PAY005", "PAY006")
def test_duplicate_rules_follow_mode(base, mode):
    a, b = base["A"], base["B"]
    first = call_function_as_api(a.uuid, [(b.uuid, 2500, "d")])
    assert first["inserted_count"] == 1

    repeat = call_function_as_api(a.uuid, [(b.uuid, 2500, "d")])
    if mode == "on":
        assert (repeat["inserted_count"], repeat["skipped_count"]) == (0, 1)
        assert repeat["gross_outgoing_cents"] == 0
    else:
        assert (repeat["inserted_count"], repeat["skipped_count"]) == (1, 0)

    if mode == "on":
        with pytest.raises(psycopg.Error) as info:
            call_function_as_api(a.uuid, [(b.uuid, 100, "new"), (b.uuid, 2501, "d")])
        assert info.value.sqlstate == "TD004"
        assert detail(info.value) == [{"index": 1, "path": "payments[1].amount"}]
    else:
        changed = call_function_as_api(a.uuid, [(b.uuid, 2501, "d")])
        assert changed["inserted_count"] == 1

    within = call_function_as_api(a.uuid, [(b.uuid, 10, "w"), (b.uuid, 10, "w"), (b.uuid, 10, "w")])
    assert within["inserted_count"] == (1 if mode == "on" else 3)

    if mode == "on":
        with pytest.raises(psycopg.Error) as info:
            call_function_as_api(a.uuid, [(b.uuid, 2500, "u"), (b.uuid, 2501, "u")])
        assert info.value.sqlstate == "TD004"


@pytest.mark.case("AMT019", "AMT020", "AMT021", "DBS007")
def test_overflow(admin):
    firms = with_balances(BASE_FIXTURE, A=2147483647, B=2147483645, C=0)
    reset_db(admin, firms)
    a, b, c = firms[0], firms[1], firms[2]
    with pytest.raises(psycopg.Error) as info:
        call_function_as_api(a.uuid, [(c.uuid, 2147483647, "x"), (b.uuid, 1, "y")])
    assert info.value.sqlstate == "TD002"  # gross exceeds balance before any range question

    with pytest.raises(psycopg.Error) as info:
        call_function_as_api(a.uuid, [(b.uuid, 1, "1"), (b.uuid, 1, "2"), (b.uuid, 1, "3")])
    assert info.value.sqlstate == "TD003"

    result = call_function_as_api(a.uuid, [(b.uuid, 1, "1"), (b.uuid, 1, "2")])
    assert result["inserted_count"] == 2
    assert snapshot().balances[b.id] == 2147483647


@pytest.mark.parametrize(
    "payer_override, entries",
    [
        (None, [{"payee_firm_uuid": "B", "amount_cents": 0, "description": "x"}]),
        (None, [{"payee_firm_uuid": "B", "amount_cents": -1, "description": "x"}]),
        (None, [{"payee_firm_uuid": "B", "amount_cents": 1.5, "description": "x"}]),
        (None, [{"payee_firm_uuid": "B", "amount_cents": 2147483648, "description": "x"}]),
        (None, [{"payee_firm_uuid": "B", "amount_cents": "1", "description": "x"}]),
        (None, []),
        (None, [{"payee_firm_uuid": "B", "amount_cents": 1, "description": f"{i}"} for i in range(1001)]),
        (None, [{"payee_firm_uuid": "B", "amount_cents": 1, "description": "x", "extra": 1}]),
        (None, [{"payee_firm_uuid": "B", "amount_cents": 1, "description": "x" * 1025}]),
        (None, [{"payee_firm_uuid": "UPPER", "amount_cents": 1, "description": "x"}]),
        (None, {"not": "an array"}),
        (None, [1]),
        (None, ["a string entry"]),
        (None, [None, {"payee_firm_uuid": "B", "amount_cents": 1, "description": "x"}]),
        (None, '[{"payee_firm_uuid": "B", "amount_cents": 1e400, "description": "x"}]'),
        (None, [{"payee_firm_uuid": 1, "amount_cents": 1, "description": "x"}]),
        (None, [{"payee_firm_uuid": "B", "amount_cents": 1, "description": 5}]),
        ("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", [{"payee_firm_uuid": "B", "amount_cents": 1, "description": "x"}]),
    ],
)
def test_internal_validation(base, payer_override, entries):
    def resolve(value):
        return {"B": base["B"].uuid, "UPPER": base["B"].uuid.upper()}.get(value, value)

    if isinstance(entries, str):  # raw JSON, for numbers Python cannot serialize (1e400)
        payload = entries.replace('"B"', json.dumps(base["B"].uuid))
    else:
        if isinstance(entries, list):
            entries = [
                {**e, "payee_firm_uuid": resolve(e["payee_firm_uuid"])} if isinstance(e, dict) else e
                for e in entries
            ]
        payload = json.dumps(entries)
    with psycopg.connect(API_DB_URL) as conn, pytest.raises(psycopg.Error) as info:
        conn.execute(
            "SELECT app.process_payment_batch(%s, %s::jsonb)",
            (payer_override or base["A"].uuid, payload),
        )
    assert info.value.sqlstate == "TD005"


@pytest.mark.case("PAY016")
def test_session_setting_cannot_override_mode(base, mode):
    result = call_function_as_api(
        base["A"].uuid,
        [(base["B"].uuid, 100, "x")],
        session_setup=f"SET app.payment_idempotency = '{OPPOSITE[mode]}'",
    )
    assert result["idempotency_mode"] == mode


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM app.firms",
        "UPDATE app.firms SET balance_cents = 0",
        "INSERT INTO app.payments (payer_firm_id, payee_firm_id, amount_cents, description) VALUES (30, 10, 1, 'x')",
        "CREATE TABLE app.extra (id integer)",
        "CREATE OR REPLACE FUNCTION app.test_hook(stage text, payer_id integer) RETURNS void LANGUAGE sql AS ''",
        "ALTER FUNCTION app.process_payment_batch(text, jsonb) SET app.payment_idempotency = 'off'",
        "SELECT app.test_hook('x', 1)",
    ],
)
def test_api_role_privileges(base, statement):
    with psycopg.connect(API_DB_URL) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute(statement)


@pytest.fixture
def scratch_url(admin):
    name = f"scratch_{uuid.uuid4().hex[:12]}"
    admin.execute(f'CREATE DATABASE "{name}"')
    yield psycopg.conninfo.make_conninfo(ADMIN_URL, dbname=name)
    admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


API_PASSWORD = os.environ.get("API_DB_PASSWORD", "")


@pytest.mark.case("DBS010", "CFG001")
def test_migrate_is_idempotent_and_preserves_data(scratch_url, mode):
    migrate(scratch_url, mode, API_PASSWORD)
    assert installed_mode(scratch_url) == mode
    with psycopg.connect(scratch_url, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM app.firms").fetchone() == (3,)
        conn.execute(
            "UPDATE app.firms SET balance_cents = balance_cents - 100 WHERE id = 1;"
            "UPDATE app.firms SET balance_cents = balance_cents + 100 WHERE id = 2;"
            "INSERT INTO app.payments (payer_firm_id, payee_firm_id, amount_cents, description)"
            " VALUES (1, 2, 100, 'kept')"
        )
        before = conn.execute("SELECT id, balance_cents FROM app.firms ORDER BY id").fetchall()

    migrate(scratch_url, mode, API_PASSWORD)

    with psycopg.connect(scratch_url) as conn:
        assert conn.execute("SELECT id, balance_cents FROM app.firms ORDER BY id").fetchall() == before
        assert conn.execute("SELECT count(*) FROM app.payments").fetchone() == (1,)
    assert installed_mode(scratch_url) == mode


@pytest.mark.case("OPS011")
def test_migrate_refuses_mode_change(scratch_url, mode):
    migrate(scratch_url, mode, API_PASSWORD)
    with pytest.raises(MigrationError, match="mode"):
        migrate(scratch_url, OPPOSITE[mode], API_PASSWORD)
    assert installed_mode(scratch_url) == mode


@pytest.mark.case("OPS011")
@pytest.mark.parametrize("bad_mode", ["ON", "", "maybe", " on"])
def test_migrate_rejects_invalid_mode(scratch_url, bad_mode):
    with pytest.raises(MigrationError):
        migrate(scratch_url, bad_mode, API_PASSWORD)
    assert installed_mode_or_none(scratch_url) is None


def installed_mode_or_none(url: str) -> str | None:
    with psycopg.connect(url) as conn:
        exists = conn.execute("SELECT to_regnamespace('app') IS NOT NULL").fetchone()[0]
    return installed_mode(url) if exists else None


@pytest.mark.case("OPS011", "CFG001")
def test_migrate_cli_exit_codes(scratch_url):
    env = {**os.environ, "ADMIN_DATABASE_URL": scratch_url}
    invalid = subprocess.run(
        [sys.executable, "-m", "app.migrate"],
        env={**env, "PAYMENT_IDEMPOTENCY_MODE": "maybe"},
        capture_output=True,
    )
    assert invalid.returncode == 2

    default = {k: v for k, v in env.items() if k != "PAYMENT_IDEMPOTENCY_MODE"}
    assert subprocess.run([sys.executable, "-m", "app.migrate"], env=default).returncode == 0
    assert installed_mode(scratch_url) == "on"

    mismatch = subprocess.run(
        [sys.executable, "-m", "app.migrate"],
        env={**env, "PAYMENT_IDEMPOTENCY_MODE": "off"},
        capture_output=True,
    )
    assert mismatch.returncode == 3
