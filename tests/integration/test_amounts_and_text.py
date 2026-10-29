"""Exact money conversion, storage boundaries and description handling end to end."""

import pytest

from tests.integration.support import (
    BASE_FIXTURE,
    MAX_CENTS,
    assert_committed,
    assert_unchanged,
    error_code,
    expected_rows,
    post_batch,
    reset_db,
    snapshot,
    with_balances,
)


def fresh(admin, **balances):
    firms = with_balances(BASE_FIXTURE, **balances)
    reset_db(admin, firms)
    return {f.alias: f for f in firms}


@pytest.mark.case("AMT001", "AMT002", "AMT003", "AMT004", "AMT013")
@pytest.mark.parametrize(
    "amount, cents",
    [("1", 100), ("300", 30000), ("6250", 625000), ("1.2", 120), ("0.1", 10), ("5800.5", 580050),
     ("1.20", 120), ("0.10", 10), ("1200.75", 120075), ("0.01", 1), ("0.29", 29), ("0.57", 57),
     ("1.01", 101), ("16.15", 1615), ("0001", 100), ("0001.20", 120), ("00.01", 1)],
)
def test_amount_representations(http, admin, amount, cents):
    firms = fresh(admin, A=1_000_000)
    before = snapshot()
    response = post_batch(http, firms["A"], [(firms["B"], amount, "amount")])
    assert response.status_code == 201
    assert response.json()["gross_outgoing_cents"] == cents
    assert_committed(before, snapshot(), [(firms["A"].id, firms["B"].id, cents, "amount")])


@pytest.mark.case("AMT004")
def test_float_sensitive_values_together(http, base):
    entries = [(base["B"], a, f"v{a}") for a in ("0.29", "0.57", "1.01", "16.15")]
    response = post_batch(http, base["A"], entries)
    assert response.json()["gross_outgoing_cents"] == 29 + 57 + 101 + 1615


@pytest.mark.case("AMT005")
@pytest.mark.parametrize("amount, count", [("0.10", 10), ("0.01", 100)])
def test_repeated_fractional_additions(http, admin, amount, count):
    firms = fresh(admin, A=100)
    entries = [(firms["B"], amount, f"part {i}") for i in range(count)]
    before = snapshot()
    response = post_batch(http, firms["A"], entries)
    assert response.status_code == 201
    assert_committed(before, snapshot(), expected_rows(firms["A"], entries))
    assert snapshot().balances[firms["A"].id] == 0


@pytest.mark.case("AMT013")
def test_all_zero_leading_zeros_rejected(http, base):
    response = post_batch(http, base["A"], [(base["B"], "000", "zero")])
    assert (response.status_code, error_code(response)) == (422, "validation_error")


@pytest.mark.case("AMT017")
def test_largest_amount(http, admin):
    firms = fresh(admin, A=MAX_CENTS, B=0, C=0)
    response = post_batch(http, firms["A"], [(firms["C"], "21474836.47", "max")])
    assert response.status_code == 201
    balances = snapshot().balances
    assert (balances[firms["A"].id], balances[firms["C"].id]) == (0, MAX_CENTS)


@pytest.mark.case("AMT018")
@pytest.mark.parametrize("amount", ["21474836.48", "99999999999999999999", "1" + "0" * 30])
def test_amount_beyond_storage(http, admin, amount):
    firms = fresh(admin, A=MAX_CENTS, B=0)
    before = snapshot()
    response = post_batch(http, firms["A"], [(firms["B"], amount, "too big")])
    assert (response.status_code, error_code(response)) == (422, "validation_error")
    assert_unchanged(before, snapshot())


@pytest.mark.case("AMT019")
def test_batch_total_beyond_storage(http, admin):
    firms = fresh(admin, A=MAX_CENTS, B=0, C=0)
    before = snapshot()
    response = post_batch(http, firms["A"], [(firms["B"], "21474836.00", "x"), (firms["C"], "0.48", "y")])
    assert (response.status_code, error_code(response)) == (422, "insufficient_funds")
    assert_unchanged(before, snapshot())


@pytest.mark.case("AMT020")
@pytest.mark.parametrize("amount, status", [("0.01", 201), ("0.02", 422)])
def test_recipient_at_storage_boundary(http, admin, amount, status):
    firms = fresh(admin, A=10000, B=MAX_CENTS - 1)
    before = snapshot()
    response = post_batch(http, firms["A"], [(firms["B"], amount, "edge")])
    assert response.status_code == status
    if status == 201:
        assert snapshot().balances[firms["B"].id] == MAX_CENTS
    else:
        assert error_code(response) == "numeric_overflow"
        assert_unchanged(before, snapshot())


@pytest.mark.case("AMT021", "DBS007")
@pytest.mark.parametrize("count, status", [(2, 201), (3, 422)])
def test_repeated_recipient_near_boundary(http, admin, count, status):
    firms = fresh(admin, A=10000, B=MAX_CENTS - 2)
    response = post_batch(http, firms["A"], [(firms["B"], "0.01", f"cent {i}") for i in range(count)])
    assert response.status_code == status
    if status == 422:
        assert error_code(response) == "numeric_overflow"


@pytest.mark.case("DBS007")
def test_wide_sums_at_limits(http, admin):
    firms = fresh(admin, A=MAX_CENTS, B=0, C=0)
    entries = [(firms["B"], "10737418.23", "half one"), (firms["B"], "10737418.24", "half two")]
    response = post_batch(http, firms["A"], entries)
    assert response.status_code == 201
    balances = snapshot().balances
    assert (balances[firms["A"].id], balances[firms["B"].id]) == (0, MAX_CENTS)


@pytest.mark.case("TXT001", "TXT002", "TXT004", "TXT007")
@pytest.mark.parametrize(
    "description",
    ["Referral fee", "Bookkeeping cleanup, 3 clients", "", "   ", "\t", "\n", " \t\n ",
     "Бухгалтерские услуги", "Belastingaangifte Café Één", "رسوم الإحالة", "转介费", "Fee 🧾✅",
     "<b>bold</b>", "<script>alert(1)</script>", "Robert'); DROP TABLE payments;--",
     "SELECT * FROM firms /* c */", "a\"b'c"],
)
def test_descriptions_stored_exactly(http, base, description):
    before = snapshot()
    response = post_batch(http, base["A"], [(base["B"], "1.00", description)])
    assert response.status_code == 201
    assert_committed(before, snapshot(), [(base["A"].id, base["B"].id, 100, description)])


@pytest.mark.case("TXT004")
def test_international_text_in_one_batch(http, base):
    texts = ["Бухгалтерия", "Één", "رسوم", "转介费", "🧾"]
    response = post_batch(http, base["A"], [(base["B"], "1.00", t) for t in texts])
    assert response.json()["inserted_count"] == 5
    assert [row[4] for row in snapshot().payments] == texts
