"""Concurrency and retry semantics across the three API instances sharing PostgreSQL.

Overlap is forced with test gates (advisory locks inside the test-only hook) and observed
in pg_stat_activity; sleeps are never used as evidence of ordering.
"""

import time

import psycopg
import pytest

from tests.integration.support import (
    ADMIN_URL,
    BASE_FIXTURE,
    Gate,
    assert_ledger,
    background,
    clear_hooks,
    error_code,
    install_hook,
    post_batch,
    reset_db,
    run_parallel,
    snapshot,
    wait_until,
    waiting_sessions,
    with_balances,
)

BOUND_SECONDS = 15


@pytest.fixture
def clients(apis):
    return list(apis.values())


def fixture(admin, **balances):
    firms = with_balances(BASE_FIXTURE, **balances)
    reset_db(admin, firms)
    return firms, {f.alias: f for f in firms}


def gated_race(admin, clients, requests, stage="after_validation"):
    """Hold every request at `stage`, then release them together; return responses in order."""
    started = time.monotonic()
    with Gate(admin, stage) as gate:
        futures = [
            background(post_batch, clients[i % len(clients)], payer, entries)
            for i, (payer, entries) in enumerate(requests)
        ]
        gate.wait_for(len(requests))
    responses = [f.result(timeout=60) for f in futures]
    assert time.monotonic() - started < BOUND_SECONDS
    assert all(r.status_code < 500 for r in responses), [r.text for r in responses]
    return responses


def sequenced(admin, clients, first, second):
    """Run `first` until it holds its row locks, queue `second` behind them, then let both finish."""
    with Gate(admin, "after_locks") as gate:
        first_future = background(post_batch, clients[0], *first)
        gate.wait_for(1)
        clear_hooks(admin)  # the second request must not stop at the gate
        second_future = background(post_batch, clients[1], *second)
        wait_until(lambda: waiting_sessions("row") >= 1)
    return first_future.result(timeout=60), second_future.result(timeout=60)


def statuses(responses):
    return sorted(r.status_code for r in responses)


@pytest.mark.case("CON001")
def test_two_competing_debits(admin, clients):
    firms, f = fixture(admin, A=10000)
    responses = gated_race(admin, clients, [
        (f["A"], [(f["B"], "80.00", "to b")]),
        (f["A"], [(f["C"], "80.00", "to c")]),
    ])
    assert statuses(responses) == [201, 422]
    assert error_code(next(r for r in responses if r.status_code == 422)) == "insufficient_funds"
    after = snapshot()
    assert after.balances[f["A"].id] == 2000
    assert len(after.payments) == 1
    assert_ledger(firms, after)


@pytest.mark.case("CON002")
@pytest.mark.parametrize("reverse", [False, True])
def test_two_debits_equal_balance(admin, clients, reverse):
    firms, f = fixture(admin, A=10000)
    one = (f["A"], [(f["B"], "60.00", "sixty")])
    two = (f["A"], [(f["C"], "40.00", "forty")])
    responses = sequenced(admin, clients, *((two, one) if reverse else (one, two)))
    assert statuses(responses) == [201, 201]
    after = snapshot()
    assert after.balances[f["A"].id] == 0
    assert_ledger(firms, after)


@pytest.mark.case("CON003")
def test_many_competing_debits(admin, clients):
    firms, f = fixture(admin, A=10000)
    requests = [(f["A"], [(f["B"] if i % 2 else f["C"], "10.00", f"debit {i}")]) for i in range(20)]
    responses = gated_race(admin, clients, requests)
    assert statuses(responses) == [201] * 10 + [422] * 10
    after = snapshot()
    assert after.balances[f["A"].id] == 0
    assert_ledger(firms, after)


@pytest.mark.case("CON004")
def test_many_one_cent_requests(admin, clients):
    firms, f = fixture(admin, A=100)
    started = time.monotonic()
    responses = run_parallel([
        (lambda i=i: post_batch(clients[i % 3], f["A"], [(f["B"], "0.01", f"cent {i}")]))
        for i in range(200)
    ])
    assert time.monotonic() - started < 60
    assert statuses(responses) == [201] * 100 + [422] * 100
    after = snapshot()
    assert after.balances[f["A"].id] == 0
    assert len(after.payments) == 100
    assert_ledger(firms, after)


@pytest.mark.case("CON005")
def test_different_payers_share_recipient(admin, clients):
    firms, f = fixture(admin, A=10000, D=10000, C=0)
    responses = gated_race(admin, clients, [
        (f["A"], [(f["C"], "30.00", "from a")]),
        (f["D"], [(f["C"], "40.00", "from d")]),
    ])
    assert statuses(responses) == [201, 201]
    after = snapshot()
    assert after.balances[f["C"].id] == 7000
    assert_ledger(firms, after)


@pytest.mark.case("CON006")
def test_opposite_direction_payments(admin, clients):
    firms, f = fixture(admin, A=10000, B=10000)
    responses = gated_race(admin, clients, [
        (f["A"], [(f["B"], "40.00", "a to b")]),
        (f["B"], [(f["A"], "30.00", "b to a")]),
    ])
    assert statuses(responses) == [201, 201]
    after = snapshot()
    assert (after.balances[f["A"].id], after.balances[f["B"].id]) == (9000, 11000)
    assert_ledger(firms, after)


@pytest.mark.case("CON007")
def test_three_firm_cycle(admin, clients):
    firms, f = fixture(admin, A=10000, B=10000, C=10000)
    responses = gated_race(admin, clients, [
        (f["A"], [(f["B"], "30.00", "a to b")]),
        (f["B"], [(f["C"], "30.00", "b to c")]),
        (f["C"], [(f["A"], "30.00", "c to a")]),
    ])
    assert statuses(responses) == [201, 201, 201]
    after = snapshot()
    assert [after.balances[f[x].id] for x in "ABC"] == [10000, 10000, 10000]
    assert_ledger(firms, after)


@pytest.mark.case("CON008")
def test_overlapping_recipients_reverse_order(admin, clients):
    firms, f = fixture(admin, A=10000, D=10000)
    responses = gated_race(admin, clients, [
        (f["A"], [(f["B"], "10.00", "a1"), (f["C"], "10.00", "a2")]),
        (f["D"], [(f["C"], "10.00", "d1"), (f["B"], "10.00", "d2")]),
    ])
    assert statuses(responses) == [201, 201]
    assert_ledger(firms, snapshot())


@pytest.mark.case("CON009")
def test_firm_pays_while_receiving(admin, clients):
    firms, f = fixture(admin)
    responses = gated_race(admin, clients, [
        (f["A"], [(f["B"], "70.00", "a pays")]),
        (f["D"], [(f["A"], "30.00", "a receives")]),
    ])
    assert statuses(responses) == [201, 201]
    after = snapshot()
    assert after.balances[f["A"].id] == 6000
    assert_ledger(firms, after)


@pytest.mark.case("CON010")
@pytest.mark.parametrize("schedule", ["incoming_first", "outgoing_first", "overlapping"])
def test_incoming_money_and_unfunded_debit(admin, clients, schedule):
    firms, f = fixture(admin, A=0, D=10000)
    incoming = (f["D"], [(f["A"], "100.00", "funding")])
    outgoing = (f["A"], [(f["B"], "80.00", "spend")])
    if schedule == "incoming_first":
        r_in, r_out = sequenced(admin, clients, incoming, outgoing)
        assert (r_in.status_code, r_out.status_code) == (201, 201)
    elif schedule == "outgoing_first":
        r_out, r_in = sequenced(admin, clients, outgoing, incoming)
        assert (r_out.status_code, r_in.status_code) == (422, 201)
    else:
        r_in, r_out = gated_race(admin, clients, [incoming, outgoing])
        assert r_in.status_code == 201
        assert r_out.status_code in (201, 422)
    assert_ledger(firms, snapshot())


@pytest.mark.case("CON011")
def test_failed_incoming_transfer_cannot_fund(admin, clients):
    firms, f = fixture(admin, A=0, D=10000)
    before = snapshot()
    with Gate(admin, "before_return", payer_id=f["D"].id) as gate:
        install_hook(admin, "before_return", "raise", payer_id=f["D"].id)
        incoming = background(post_batch, clients[0], f["D"], [(f["A"], "100.00", "will fail")])
        gate.wait_for(1)
        outgoing = background(post_batch, clients[1], f["A"], [(f["B"], "80.00", "spend")])
        wait_until(lambda: waiting_sessions("row") >= 1)
    assert incoming.result(timeout=30).status_code == 500
    response = outgoing.result(timeout=30)
    assert (response.status_code, error_code(response)) == (422, "insufficient_funds")
    assert snapshot() == before


@pytest.mark.case("CON016")
def test_waits_for_held_shared_firm(admin, clients):
    firms, f = fixture(admin)
    with psycopg.connect(ADMIN_URL) as blocker:
        blocker.execute("SELECT 1 FROM app.firms WHERE id = %s FOR UPDATE", (f["B"].id,))
        pending = background(post_batch, clients[0], f["A"], [(f["B"], "10.00", "waits")])
        wait_until(lambda: waiting_sessions("row") >= 1)
        assert not pending.done()
        blocker.rollback()
    assert pending.result(timeout=30).status_code == 201
    assert_ledger(firms, snapshot())


@pytest.mark.case("CON017")
def test_unrelated_held_firm_does_not_block(admin, clients):
    firms, f = fixture(admin)
    with psycopg.connect(ADMIN_URL) as blocker:
        blocker.execute("SELECT 1 FROM app.firms WHERE id = %s FOR UPDATE", (f["D"].id,))
        started = time.monotonic()
        response = post_batch(clients[0], f["A"], [(f["B"], "10.00", "free path")])
        assert time.monotonic() - started < 1.5
        assert response.status_code == 201
        blocker.rollback()


@pytest.mark.case("CON018", "FRM008")
def test_uuid_order_and_id_order_differ(admin, clients):
    firms, f = fixture(admin, A=10000, B=10000, C=10000, D=10000)
    requests = [
        (f["A"], [(f["D"], "1.00", "a-d"), (f["C"], "1.00", "a-c"), (f["B"], "1.00", "a-b")]),
        (f["D"], [(f["B"], "1.00", "d-b"), (f["C"], "1.00", "d-c"), (f["A"], "1.00", "d-a")]),
        (f["B"], [(f["A"], "1.00", "b-a"), (f["D"], "1.00", "b-d")]),
        (f["C"], [(f["B"], "1.00", "c-b"), (f["A"], "1.00", "c-a"), (f["D"], "1.00", "c-d")]),
    ]
    responses = gated_race(admin, clients, requests)
    assert statuses(responses) == [201] * 4
    after = snapshot()
    assert len(after.payments) == 11
    assert_ledger(firms, after)


@pytest.mark.case("CON019")
def test_balance_changes_while_request_is_paused(admin, clients):
    firms, f = fixture(admin, A=10000)
    with Gate(admin, "after_validation", payer_id=f["A"].id) as gate:
        paused = background(post_batch, clients[0], f["A"], [(f["B"], "80.00", "paused")])
        gate.wait_for(1)
        clear_hooks(admin)
        assert post_batch(clients[1], f["A"], [(f["C"], "50.00", "finishes first")]).status_code == 201
    response = paused.result(timeout=30)
    assert (response.status_code, error_code(response)) == (422, "insufficient_funds")
    after = snapshot()
    assert after.balances[f["A"].id] == 5000
    assert_ledger(firms, after)


@pytest.mark.case("CON020")
def test_mixed_workload(admin, clients):
    firms, f = fixture(admin, A=10000, B=10000, C=10000, D=10000)
    requests = []
    for i in range(6):
        requests.append((f["A"], [(f["B"], "5.00", f"same payer {i}")]))
        requests.append((f["C"], [(f["B"], "3.00", f"shared recipient {i}")]))
        requests.append((f["D"], [(f["D"], "1.00", f"disjoint self {i}")]))
    responses = gated_race(admin, clients, requests)
    assert statuses(responses) == [201] * 18
    after = snapshot()
    assert after.balances[f["B"].id] == 10000 + 6 * 500 + 6 * 300
    assert_ledger(firms, after)


@pytest.mark.case("CON021")
@pytest.mark.parametrize("large_first", [True, False])
def test_large_and_small_batches_overlap(admin, clients, large_first):
    firms, f = fixture(admin, A=100000, D=10000)
    large = (f["A"], [(f["B"] if i % 2 else f["C"], "1.00", f"large {i}") for i in range(200)])
    small = (f["D"], [(f["B"], "10.00", "small")])
    responses = sequenced(admin, clients, *((large, small) if large_first else (small, large)))
    assert statuses(responses) == [201, 201]
    after = snapshot()
    assert len(after.payments) == 201
    assert_ledger(firms, after)


@pytest.mark.case("CON022")
@pytest.mark.parametrize(
    "stage", ["after_locks", "after_payer_balance", "after_payee_balance", "after_payment_insert", "before_return"]
)
def test_observer_never_sees_partial_batch(admin, clients, stage):
    firms, f = fixture(admin)
    before = snapshot()
    with Gate(admin, stage) as gate:
        pending = background(
            post_batch, clients[0], f["A"], [(f["B"], "10.00", "b"), (f["C"], "20.00", "c"), (f["D"], "30.00", "d")]
        )
        gate.wait_for(1)
        assert snapshot() == before
    assert pending.result(timeout=30).status_code == 201
    after = snapshot()
    assert len(after.payments) == 3
    assert_ledger(firms, after)


@pytest.mark.case("PAY007", "NET004")
def test_concurrent_identical_payments(admin, clients, mode):
    firms, f = fixture(admin)
    entry = [(f["B"], "25.00", "invoice 42")]
    responses = gated_race(admin, clients, [(f["A"], entry), (f["A"], entry)])
    assert statuses(responses) == [201, 201]
    inserted = sorted(r.json()["inserted_count"] for r in responses)
    assert inserted == ([0, 1] if mode == "on" else [1, 1])
    after = snapshot()
    assert len(after.payments) == (1 if mode == "on" else 2)
    assert_ledger(firms, after)


@pytest.mark.case("PAY008")
def test_concurrent_unequal_amounts_for_one_key(admin, clients, mode):
    firms, f = fixture(admin)
    responses = gated_race(admin, clients, [
        (f["A"], [(f["B"], "25.00", "invoice 42")]),
        (f["A"], [(f["B"], "26.00", "invoice 42")]),
    ])
    if mode == "on":
        assert statuses(responses) == [201, 409]
        assert len(snapshot().payments) == 1
    else:
        assert statuses(responses) == [201, 201]
        assert len(snapshot().payments) == 2
    assert_ledger(firms, snapshot())


@pytest.mark.case("PAY015")
@pytest.mark.parametrize("shared_conflict", [False, True])
def test_concurrent_overlapping_mixed_batches(admin, clients, mode, shared_conflict):
    firms, f = fixture(admin)
    first = [(f["B"], "10.00", "shared"), (f["C"], "1.00", "new one")]
    second = [(f["B"], "10.01" if shared_conflict else "10.00", "shared"), (f["D"], "2.00", "new two")]
    responses = gated_race(admin, clients, [(f["A"], first), (f["A"], second)])
    rows = len(snapshot().payments)
    if mode == "off":
        assert statuses(responses) == [201, 201]
        assert rows == 4
    elif shared_conflict:
        assert statuses(responses) == [201, 409]
        assert rows == 2
    else:
        assert statuses(responses) == [201, 201]
        assert rows == 3
    assert_ledger(firms, snapshot())


@pytest.mark.case("SEQ008", "PAY011")
def test_same_amount_spellings_concurrently(admin, clients, mode):
    firms, f = fixture(admin)
    responses = gated_race(admin, clients, [(f["A"], [(f["B"], s, "same key")]) for s in ("25", "25.0", "25.00")])
    assert statuses(responses) == [201, 201, 201]
    assert len(snapshot().payments) == (1 if mode == "on" else 3)


@pytest.mark.case("NET004")
def test_retry_while_first_attempt_runs(admin, clients, mode):
    firms, f = fixture(admin)
    entries = [(f["B"], "25.00", "retried")]
    with Gate(admin, "before_return") as gate:
        first = background(post_batch, clients[0], f["A"], entries)
        gate.wait_for(1)
        clear_hooks(admin)
        second = background(post_batch, clients[1], f["A"], entries)
        wait_until(lambda: waiting_sessions("row") >= 1)
    r1, r2 = first.result(timeout=30), second.result(timeout=30)
    assert (r1.status_code, r2.status_code) == (201, 201)
    assert r2.json()["inserted_count"] == (0 if mode == "on" else 1)
    assert_ledger(firms, snapshot())


@pytest.mark.case("NET005")
def test_retry_after_lost_response(http, admin, mode):
    firms, f = fixture(admin)
    entries = [(f["B"], "25.00", "lost response")]
    post_batch(http, f["A"], entries)  # response deliberately discarded
    retry = post_batch(http, f["A"], entries)
    assert retry.status_code == 201
    assert retry.json()["inserted_count"] == (0 if mode == "on" else 1)
    assert len(snapshot().payments) == (1 if mode == "on" else 2)


@pytest.mark.case("NET008")
def test_retry_reaches_another_instance(apis, admin, mode):
    firms, f = fixture(admin)
    entries = [(f["B"], "25.00", "other instance")]
    post_batch(apis["api-1"], f["A"], entries)  # response deliberately discarded
    retry = post_batch(apis["api-2"], f["A"], entries)
    assert retry.status_code == 201
    assert retry.json()["inserted_count"] == (0 if mode == "on" else 1)
    assert_ledger(firms, snapshot())


@pytest.mark.case("NET010")
def test_delayed_duplicate_after_other_payments(http, admin, mode):
    firms, f = fixture(admin, A=10000)
    original = [(f["B"], "25.00", "original")]
    assert post_batch(http, f["A"], original).status_code == 201
    assert post_batch(http, f["A"], [(f["B"], "10.00", "later one")]).status_code == 201
    assert post_batch(http, f["B"], [(f["A"], "5.00", "later two")]).status_code == 201
    late = post_batch(http, f["A"], original)
    assert late.status_code == 201
    assert late.json()["inserted_count"] == (0 if mode == "on" else 1)
    assert_ledger(firms, snapshot())
