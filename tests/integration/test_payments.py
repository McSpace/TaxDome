"""Sequential business behavior through Nginx: funds, self-payments, batches and duplicates."""

from itertools import permutations

import pytest

from tests.integration.support import (
    ABSENT_UUID,
    BASE_FIXTURE,
    Firm,
    assert_committed,
    assert_unchanged,
    error_code,
    expected_rows,
    post_batch,
    reset_db,
    snapshot,
    with_balances,
)


def pay(http, payer, entries, status=201, code=None):
    """Post a batch and check the status; on success verify rows and balances exactly."""
    before = snapshot()
    response = post_batch(http, payer, entries)
    assert response.status_code == status, response.text
    after = snapshot()
    if status == 201:
        if response.json()["skipped_count"] == 0:
            assert_committed(before, after, expected_rows(payer, entries))
    else:
        assert error_code(response) == code
        assert_unchanged(before, after)
    return response


def fixture(admin, **balances) -> dict[str, Firm]:
    firms = with_balances(BASE_FIXTURE, **balances)
    reset_db(admin, firms)
    return {f.alias: f for f in firms}


@pytest.mark.case("BAS001", "BAS012")
def test_one_payment(http, base):
    pay(http, base["A"], [(base["B"], "25.00", "Referral fee")])


@pytest.mark.case("BAS002")
def test_several_recipients(http, base):
    pay(http, base["A"], [(base["B"], "10.00", "b"), (base["C"], "15.25", "c"), (base["D"], "20.50", "d")])


@pytest.mark.case("BAS003")
def test_several_entries_for_one_recipient(http, base):
    pay(http, base["A"], [(base["B"], "10.00", "first"), (base["B"], "15.00", "second")])


@pytest.mark.case("BAS004", "PAY005")
@pytest.mark.parametrize("copies", [2, 3])
def test_identical_entries_in_one_request(http, base, mode, copies):
    a, b = base["A"], base["B"]
    before = snapshot()
    response = post_batch(http, a, [(b, "10.00", "same")] * copies)
    assert response.status_code == 201
    inserted = 1 if mode == "on" else copies
    assert response.json() == {
        "inserted_count": inserted,
        "skipped_count": copies - inserted,
        "gross_outgoing_cents": 1000 * inserted,
        "idempotency_mode": mode,
    }
    assert_committed(before, snapshot(), [(a.id, b.id, 1000, "same")] * inserted)


@pytest.mark.case("BAS006", "BAS007", "BAS008", "BAS009", "BAS010")
@pytest.mark.parametrize(
    "balance, amount, status",
    [(10000, "100.00", 201), (10000, "99.99", 201), (10000, "100.01", 422), (0, "0.01", 422), (10000, "0.01", 201)],
)
def test_balance_edges(http, admin, balance, amount, status):
    firms = fixture(admin, A=balance)
    pay(http, firms["A"], [(firms["B"], amount, "edge")], status, None if status == 201 else "insufficient_funds")


@pytest.mark.case("BAS011", "BAS013")
def test_zero_balance_recipient_and_other_payer(http, base):
    pay(http, base["A"], [(base["C"], "25.00", "to zero balance")])
    pay(http, base["D"], [(base["C"], "10.00", "other payer")])


@pytest.mark.case("BAS014")
def test_equal_names_different_firms(http, admin):
    firms = [f if f.alias not in "BC" else Firm(f.alias, f.id, f.uuid, f.cents, "Same Name LLC") for f in BASE_FIXTURE]
    reset_db(admin, firms)
    a, b, c = firms[0], firms[1], firms[2]
    pay(http, a, [(b, "10.00", "to b"), (c, "10.00", "to c")])


@pytest.mark.case("BAS015")
def test_unrelated_firms_untouched(http, admin):
    extra = [Firm(f"E{i}", 100 + i, f"eeeeeeee-eeee-4eee-8eee-{i:012d}", 1000 * i, f"Extra {i}") for i in range(10)]
    reset_db(admin, [*BASE_FIXTURE, *extra])
    pay(http, BASE_FIXTURE[0], [(BASE_FIXTURE[1], "25.00", "x")])
    balances = snapshot().balances
    assert all(balances[f.id] == f.cents for f in extra)


@pytest.mark.case("FRM001", "FRM002", "FRM003")
@pytest.mark.parametrize("position", [0, 1, 2])
def test_unknown_recipient_in_any_position(http, base, position):
    entries = [(base["B"], "1.00", "b"), (base["C"], "1.00", "c")]
    entries.insert(position, (ABSENT_UUID, "1.00", "x"))
    before = snapshot()
    response = post_batch(http, base["A"], entries)
    assert (response.status_code, error_code(response)) == (422, "unknown_firm")
    assert response.json()["error"]["details"] == [
        {"index": position, "path": f"payments[{position}].payee_firm_uuid"}
    ]
    assert_unchanged(before, snapshot())


@pytest.mark.case("FRM001")
def test_unknown_payer(http, base):
    before = snapshot()
    response = post_batch(http, ABSENT_UUID, [(base["B"], "10.00", "x")])
    assert (response.status_code, error_code(response)) == (422, "unknown_firm")
    assert_unchanged(before, snapshot())


@pytest.mark.case("FRM005")
def test_uuid_letter_case(http, base):
    a, b = base["A"], base["B"]
    mixed = "".join(ch.upper() if i % 2 else ch for i, ch in enumerate(b.uuid))
    for index, (payer, payee) in enumerate([(a.uuid.upper(), b.uuid), (a.uuid, b.uuid.upper()), (a.uuid, mixed)]):
        before = snapshot()
        response = post_batch(http, payer, [(payee, "1.00", f"case {index}")])
        assert response.status_code == 201
        assert_committed(before, snapshot(), [(a.id, b.id, 100, f"case {index}")])

    before = snapshot()
    response = post_batch(http, a.uuid.upper(), [(a.uuid, "97.00", "self, mixed case")])
    assert response.status_code == 201
    after = snapshot()
    assert after.balances == before.balances
    assert after.rows_without_ids()[-1] == (a.id, a.id, 9700, "self, mixed case")


@pytest.mark.case("FRM008", "BAT002")
@pytest.mark.parametrize("order", list(permutations("BCD")))
def test_recipient_order_does_not_matter(http, admin, order):
    firms = fixture(admin, A=10000)
    amounts = {"B": "10.00", "C": "20.00", "D": "70.00"}
    pay(http, firms["A"], [(firms[x], amounts[x], f"to {x}") for x in order])
    assert snapshot().balances[firms["A"].id] == 0


@pytest.mark.case("BAT001")
def test_combined_amount_exceeds_balance(http, admin):
    firms = fixture(admin, A=10000)
    pay(http, firms["A"], [(firms["B"], "60.00", "b"), (firms["C"], "60.00", "c")], 422, "insufficient_funds")


@pytest.mark.case("BAT005", "BAT006", "BAT007")
@pytest.mark.parametrize("amount, status", [("25.00", 201), ("100.00", 201), ("100.01", 422)])
def test_self_payment(http, admin, amount, status):
    firms = fixture(admin, A=10000)
    a = firms["A"]
    before = snapshot()
    response = post_batch(http, a, [(a, amount, "self")])
    assert response.status_code == status
    after = snapshot()
    assert after.balances == before.balances
    if status == 201:
        assert after.rows_without_ids() == expected_rows(a, [(a, amount, "self")])
    else:
        assert error_code(response) == "insufficient_funds"
        assert after.payments == []


@pytest.mark.case("BAT008")
@pytest.mark.parametrize("reverse", [False, True])
def test_self_plus_external_needs_gross(http, admin, reverse):
    firms = fixture(admin, A=10000)
    entries = [(firms["A"], "100.00", "self"), (firms["B"], "100.00", "external")]
    pay(http, firms["A"], entries[::-1] if reverse else entries, 422, "insufficient_funds")


@pytest.mark.case("BAT009")
@pytest.mark.parametrize("order", [(0, 1, 2), (2, 0, 1), (1, 2, 0)])
def test_several_self_payments_plus_others(http, admin, order):
    firms = fixture(admin, A=10000)
    a, b = firms["A"], firms["B"]
    entries = [(a, "20.00", "self one"), (a, "20.00", "self two"), (b, "60.00", "external")]
    pay(http, a, [entries[i] for i in order])
    assert snapshot().balances[a.id] == 4000


@pytest.mark.case("BAT010")
@pytest.mark.parametrize("last, status", [("50.01", 422), ("49.99", 201), ("50.00", 201)])
def test_one_cent_change_to_total(http, admin, last, status):
    firms = fixture(admin, A=10000)
    entries = [(firms["B"], "50.00", "first"), (firms["C"], last, "second")]
    pay(http, firms["A"], entries, status, None if status == 201 else "insufficient_funds")


@pytest.mark.case("BAT011")
def test_mixed_amount_formats(http, base):
    response = pay(http, base["A"], [(base["B"], "1", "one"), (base["B"], "1.0", "two"), (base["B"], "1.00", "three")])
    assert response.json()["gross_outgoing_cents"] == 300


@pytest.mark.case("SEQ001")
def test_two_batches_from_one_payer(http, admin):
    firms = fixture(admin, A=10000)
    pay(http, firms["A"], [(firms["B"], "30.00", "first")])
    pay(http, firms["A"], [(firms["C"], "40.00", "second")])
    assert snapshot().balances[firms["A"].id] == 3000


@pytest.mark.case("SEQ002", "PAY001")
def test_repeated_payload(http, base, mode):
    a, b = base["A"], base["B"]
    pay(http, a, [(b, "25.00", "d")])
    before = snapshot()
    response = post_batch(http, a, [(b, "25.00", "d")])
    assert response.status_code == 201
    if mode == "on":
        assert (response.json()["inserted_count"], response.json()["skipped_count"]) == (0, 1)
        assert_unchanged(before, snapshot())
    else:
        assert_committed(before, snapshot(), [(a.id, b.id, 2500, "d")])


@pytest.mark.case("SEQ004")
def test_payer_receives_funds_between_calls(http, admin):
    firms = fixture(admin, A=0, D=10000)
    a, b, d = firms["A"], firms["B"], firms["D"]
    pay(http, a, [(b, "25.00", "to b")], 422, "insufficient_funds")
    pay(http, d, [(a, "50.00", "funding")])
    pay(http, a, [(b, "25.00", "to b")])
    assert snapshot().balances[a.id] == 2500


@pytest.mark.case("SEQ005")
def test_payer_spends_between_calls(http, admin):
    firms = fixture(admin, A=10000)
    pay(http, firms["A"], [(firms["B"], "80.00", "first")])
    pay(http, firms["A"], [(firms["C"], "80.00", "second")], 422, "insufficient_funds")


@pytest.mark.case("SEQ006")
def test_receiver_later_pays(http, base):
    pay(http, base["A"], [(base["C"], "30.00", "to c")])
    pay(http, base["C"], [(base["B"], "20.00", "c to b")])
    assert snapshot().balances[base["C"].id] == 1000


@pytest.mark.case("SEQ007")
def test_transfers_both_directions(http, base):
    pay(http, base["A"], [(base["B"], "25.00", "a to b")])
    pay(http, base["B"], [(base["A"], "10.00", "b to a")])
    balances = snapshot().balances
    assert (balances[base["A"].id], balances[base["B"].id]) == (8500, 3500)


@pytest.mark.case("SEQ008", "PAY011")
def test_same_amount_different_spelling_sequential(http, base, mode):
    a, b = base["A"], base["B"]
    results = [post_batch(http, a, [(b, spelling, "same key")]).json() for spelling in ("25", "25.0", "25.00")]
    assert [r["inserted_count"] for r in results] == ([1, 0, 0] if mode == "on" else [1, 1, 1])
    assert len(snapshot().payments) == (1 if mode == "on" else 3)


@pytest.mark.case("PAY011")
def test_same_amount_different_spelling_in_one_batch(http, base, mode):
    a, b = base["A"], base["B"]
    response = post_batch(http, a, [(b, s, "same key") for s in ("25", "25.0", "25.00")])
    assert response.status_code == 201
    assert response.json()["inserted_count"] == (1 if mode == "on" else 3)


@pytest.mark.case("SEQ010")
def test_many_sequential_debits(http, admin):
    firms = fixture(admin, A=10000)
    statuses = [post_batch(http, firms["A"], [(firms["B"], "10.00", f"debit {i}")]).status_code for i in range(20)]
    assert statuses == [201] * 10 + [422] * 10
    after = snapshot()
    assert after.balances[firms["A"].id] == 0
    assert len(after.payments) == 10


@pytest.mark.case("PAY002")
def test_changed_amount_for_history_key(http, base, mode):
    a, b = base["A"], base["B"]
    pay(http, a, [(b, "25.00", "d")])
    if mode == "on":
        pay(http, a, [(b, "25.01", "d")], 409, "payment_amount_conflict")
    else:
        pay(http, a, [(b, "25.01", "d")])


@pytest.mark.case("PAY003")
def test_new_payments_mixed_with_repeats(http, base, mode):
    a, b, c = base["A"], base["B"], base["C"]
    pay(http, a, [(b, "25.00", "d")])
    before = snapshot()
    response = post_batch(http, a, [(b, "25.00", "d"), (c, "10.00", "new")])
    assert response.status_code == 201
    if mode == "on":
        assert response.json()["skipped_count"] == 1
        assert_committed(before, snapshot(), [(a.id, c.id, 1000, "new")])
    else:
        assert_committed(before, snapshot(), [(a.id, b.id, 2500, "d"), (a.id, c.id, 1000, "new")])


@pytest.mark.case("PAY004")
@pytest.mark.parametrize("conflict_first", [True, False])
def test_conflict_mixed_with_new(http, base, mode, conflict_first):
    a, b, c = base["A"], base["B"], base["C"]
    pay(http, a, [(b, "25.00", "d")])
    entries = [(b, "25.01", "d"), (c, "10.00", "new")]
    entries = entries if conflict_first else entries[::-1]
    if mode == "on":
        pay(http, a, entries, 409, "payment_amount_conflict")
    else:
        pay(http, a, entries)


@pytest.mark.case("PAY006")
@pytest.mark.parametrize("order", [("25.00", "25.01"), ("25.01", "25.00")])
def test_unequal_amounts_one_key_in_batch(http, base, mode, order):
    a, b = base["A"], base["B"]
    entries = [(b, amount, "k") for amount in order]
    if mode == "on":
        response = pay(http, a, entries, 409, "payment_amount_conflict")
        assert response.json()["error"]["details"] == [{"index": 1, "path": "payments[1].amount"}]
    else:
        pay(http, a, entries)


@pytest.mark.case("PAY009", "TXT005")
def test_description_variants_are_distinct_keys(http, base):
    a, b = base["A"], base["B"]
    variants = ["d", "D", "d ", " d", "d​", "café", "café"]
    response = pay(http, a, [(b, "1.00", v) for v in variants])
    assert response.json()["inserted_count"] == len(variants)
    assert [row[4] for row in snapshot().payments] == variants


@pytest.mark.case("TXT005")
def test_normalization_forms_in_separate_calls(http, base):
    a, b = base["A"], base["B"]
    for text in ("Résumé review", "Résumé review"):
        assert post_batch(http, a, [(b, "1.00", text)]).json()["inserted_count"] == 1


@pytest.mark.case("PAY010", "TXT008")
def test_same_description_for_different_keys(http, base):
    a, b, c, d = base["A"], base["B"], base["C"], base["D"]
    pay(http, a, [(b, "5.00", "Referral fee")])
    pay(http, a, [(c, "5.00", "Referral fee")])
    pay(http, d, [(b, "5.00", "Referral fee")])
    assert len(snapshot().payments) == 3


@pytest.mark.case("TXT008")
def test_same_description_different_amounts_same_payee(http, base, mode):
    a, b = base["A"], base["B"]
    entries = [(b, "5.00", "Monthly"), (b, "6.00", "Monthly")]
    if mode == "on":
        pay(http, a, entries, 409, "payment_amount_conflict")
    else:
        pay(http, a, entries)


@pytest.mark.case("PAY012")
def test_all_repeats_after_balance_spent(http, admin, mode):
    firms = fixture(admin, A=10000)
    a, b, c = firms["A"], firms["B"], firms["C"]
    pay(http, a, [(b, "25.00", "d")])
    pay(http, a, [(c, "75.00", "spend the rest")])
    if mode == "on":
        response = pay(http, a, [(b, "25.00", "d")])
        assert response.json() == {
            "inserted_count": 0, "skipped_count": 1, "gross_outgoing_cents": 0, "idempotency_mode": "on"
        }
    else:
        pay(http, a, [(b, "25.00", "d")], 422, "insufficient_funds")


@pytest.mark.case("PAY013")
def test_mixed_batch_needs_only_new_gross(http, admin, mode):
    firms = fixture(admin, A=10000)
    a, b, c = firms["A"], firms["B"], firms["C"]
    pay(http, a, [(b, "50.00", "historical")])
    entries = [(b, "50.00", "historical"), (c, "40.00", "new")]
    if mode == "on":
        before = snapshot()
        response = post_batch(http, a, entries)
        assert response.status_code == 201
        assert response.json()["gross_outgoing_cents"] == 4000
        assert_committed(before, snapshot(), [(a.id, c.id, 4000, "new")])
    else:
        pay(http, a, entries, 422, "insufficient_funds")


@pytest.mark.case("PAY014")
def test_self_payment_repeats_and_conflicts(http, base, mode):
    a = base["A"]
    pay(http, a, [(a, "25.00", "self")])
    repeat = post_batch(http, a, [(a, "25.00", "self")])
    assert repeat.status_code == 201
    assert repeat.json()["inserted_count"] == (0 if mode == "on" else 1)
    if mode == "on":
        pay(http, a, [(a, "30.00", "self")], 409, "payment_amount_conflict")
    else:
        pay(http, a, [(a, "30.00", "self")])
    assert snapshot().balances[a.id] == 10000
