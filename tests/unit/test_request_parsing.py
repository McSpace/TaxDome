"""Unit tests for byte-level request parsing and field validation.

Catalogue IDs in comments map these inputs to docs/Firm_Payments_Test_Scenarios.md;
the same inputs are exercised end to end in tests/integration.
"""

import json

import pytest

from app.errors import ApiError
from app.request_parsing import (
    MAX_BODY_BYTES,
    BatchRequest,
    PaymentEntry,
    parse_amount,
    parse_batch_request,
)

PAYER = "3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41"
PAYEE = "8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10"
JSON_CT = "application/json"


def entry(amount="10.00", payee=PAYEE, description="Referral fee"):
    return {"amount": amount, "payee_firm_uuid": payee, "description": description}


DEFAULT = object()


def body(payments=DEFAULT, payer=PAYER, **extra):
    doc = {"payer_firm_uuid": payer, "payments": [entry()] if payments is DEFAULT else payments}
    doc.update(extra)
    return json.dumps(doc).encode()


def expect_error(status, code, raw, content_type=JSON_CT):
    with pytest.raises(ApiError) as info:
        parse_batch_request(raw, content_type)
    assert (info.value.status, info.value.code) == (status, code)
    return info.value


# AMT001-AMT004, AMT013, AMT017, BAT011, PAY011
@pytest.mark.parametrize(
    "text, cents",
    [
        ("1", 100),
        ("300", 30000),
        ("6250", 625000),
        ("5800.5", 580050),
        ("1.2", 120),
        ("0.1", 10),
        ("1.20", 120),
        ("0.01", 1),
        ("1200.75", 120075),
        ("0.29", 29),
        ("0.57", 57),
        ("1.01", 101),
        ("16.15", 1615),
        ("25", 2500),
        ("25.0", 2500),
        ("25.00", 2500),
        ("0001", 100),
        ("0001.20", 120),
        ("00.01", 1),
        ("21474836.47", 2147483647),
        ("0" * 31 + "1", 100),
    ],
)
def test_parse_amount_valid(text, cents):
    assert parse_amount(text) == cents


# AMT006-AMT012, AMT014, AMT015, AMT018, OPS004
@pytest.mark.parametrize(
    "text",
    [
        "0", "0.0", "0.00", "000.00", "000",
        "-1", "-0.01", "-0.00", "+1.00",
        "1.001", "1.999", "0.0001", "1.2300",
        "1e2", "1E+2", "1e-2",
        "1,25", "1,000.00", "1 000.00", "$1.00", "€1.00",
        " 1.00", "1.00 ", "\t1.00", "1.00\n",
        ".50", "1.", ".", "", "   ",
        "١", "１", "−1",
        "NaN", "Infinity", "-Infinity", "null", "one",
        "21474836.48", "9" * 33, "0" * 5000 + "1", "9" * 5000,
    ],
)
def test_parse_amount_invalid(text):
    with pytest.raises(ApiError) as info:
        parse_amount(text)
    assert (info.value.status, info.value.code) == (422, "validation_error")


# REQ015, REQ016
@pytest.mark.parametrize(
    "content_type", [None, "", "text/plain", "application/xml", "application/json; charset=latin-1"]
)
def test_media_type_rejected(content_type):
    expect_error(415, "unsupported_media_type", body(), content_type)


@pytest.mark.parametrize(
    "content_type", ["application/json", "application/json; charset=UTF-8", "Application/JSON;charset=utf-8"]
)
def test_media_type_accepted(content_type):
    assert parse_batch_request(body(), content_type).payer_firm_uuid == PAYER


# REQ001-REQ003, REQ014, REQ016, AMT015 (bare NaN), Review Focus 2
@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"  \n",
        b'{"payer_firm_uuid": "x", "payments": [',
        b'{"payer_firm_uuid": "x",}',
        b"{payer_firm_uuid: 1}",
        b'{"payer_firm_uuid": "abc}',
        b'{"payer_firm_uuid": "x" // comment\n}',
        b'{"payer_firm_uuid": /* c */ "x"}',
        b"\xef\xbb\xbf" + body(),
        b'{"payer_firm_uuid": "\xff"}',
        ('{"payer_firm_uuid": "%s", "payer_firm_uuid": "%s", "payments": []}' % (PAYER, PAYEE)).encode(),
        ('{"payer_firm_uuid": "%s", "payments": [{"amount": "1", "amount": "2", '
         '"payee_firm_uuid": "%s", "description": ""}]}' % (PAYER, PAYEE)).encode(),
        ('{"payer_firm_uuid": "%s", "payments": [], "payments": []}' % PAYER).encode(),
        ('{"payer_firm_uuid": "%s", "payments": [{"amount": NaN}]}' % PAYER).encode(),
        b"Infinity",
        b"1" + b"0" * 5000,
        b"[" * 100000,
    ],
)
def test_invalid_json(raw):
    expect_error(400, "invalid_json", raw)


def test_body_over_limit_is_413():
    expect_error(413, "request_too_large", b" " * (MAX_BODY_BYTES + 1))


# REQ004-REQ013, AMT016, FRM004, FRM006, FRM007, TXT003, TXT006, OPS001, OPS003, Review Focus 1
@pytest.mark.parametrize(
    "raw",
    [
        b"null", b"[]", b'"s"', b"1", b"true",
        json.dumps({"payments": [entry()]}).encode(),
        json.dumps({"payer_firm_uuid": PAYER}).encode(),
        *[body(payments=v) for v in (None, {}, "x", 1, True)],
        body(payments=[]),
        body(payments=[entry(description=f"d{i}") for i in range(1001)]),
        *[body(payments=[v]) for v in (None, "x", [], 1, True)],
        body(payments=[entry(), None, entry(description="other")]),
        *[body(payments=[{k: v for k, v in entry().items() if k != f}]) for f in ("amount", "payee_firm_uuid", "description")],
        body(mode="off"),
        body(request_note="n", internal_id=1),
        body(payments=[{**entry(), "currency": "USD"}]),
        body(payments=[{**entry(), "amount_cents": 100}]),
        *[body(payments=[entry(amount=v)]) for v in (1, 1.25, True, None, [], {})],
        *[body(payer=v) for v in (None, 1, True, [], {})],
        *[body(payments=[entry(payee=v)]) for v in (None, 1, False, [PAYEE], {"u": PAYEE})],
        *[body(payer=v) for v in (
            PAYER[:-1], PAYER.replace("3f", "zz"), "not a uuid", "{" + PAYER + "}",
            "urn:uuid:" + PAYER, " " + PAYER, PAYER + " ", "\t" + PAYER, PAYER + "\n",
            PAYER.replace("-", ""), "1", "30",
        )],
        body(payments=[entry(payee="30")]),
        *[body(payments=[entry(description=v)]) for v in (None, 1, True, [], {})],
        body(payments=[entry(description="x" * 1025)]),
        body(payments=[entry(description="😀" * 1025)]),
        body(payments=[entry(description="a\u0000b")]),
        b'{"payer_firm_uuid": "%s", "payments": [{"amount": "1", "payee_firm_uuid": "%s", '
        b'"description": "\\ud800"}]}' % (PAYER.encode(), PAYEE.encode()),
    ],
)
def test_validation_errors(raw):
    expect_error(422, "validation_error", raw)


# OPS001, OPS003, TXT002, TXT006, FRM005, REQ018
def test_valid_edges():
    many = parse_batch_request(body(payments=[entry(description=f"d{i}") for i in range(1000)]), JSON_CT)
    assert len(many.payments) == 1000

    for description in ("", "   ", "\t\n", "😀" * 1024, "x" * 1024, 'q"uote\\back\nnl\ttab'):
        parsed = parse_batch_request(body(payments=[entry(description=description)]), JSON_CT)
        assert parsed.payments[0].description == description

    upper = parse_batch_request(body(payer=PAYER.upper(), payments=[entry(payee=PAYEE.upper())]), JSON_CT)
    assert upper.payer_firm_uuid == PAYER
    assert upper.payments[0].payee_firm_uuid == PAYEE

    compact = body()
    pretty = json.dumps(
        {"payments": [{"description": "Referral fee", "amount": "10.00", "payee_firm_uuid": PAYEE}],
         "payer_firm_uuid": PAYER},
        indent=4,
    ).encode()
    expected = BatchRequest(PAYER, (PaymentEntry(PAYEE, 1000, "Referral fee"),))
    assert parse_batch_request(compact, JSON_CT) == expected
    assert parse_batch_request(pretty, JSON_CT) == expected


# BAT012
def test_errors_aggregate_in_order():
    payments = [
        {"amount": "1.00", "payee_firm_uuid": PAYEE},
        entry(),
        entry(amount="1.001"),
    ]
    error = expect_error(422, "validation_error", body(payments=payments))
    assert [(d["index"], d["path"]) for d in error.details] == [
        (0, "payments[0].description"),
        (2, "payments[2].amount"),
    ]


def test_envelope_shape():
    error = ApiError(422, "insufficient_funds", "Payer balance cannot cover new outgoing payments.")
    assert error.envelope() == {
        "error": {"code": "insufficient_funds", "message": "Payer balance cannot cover new outgoing payments."}
    }
    detailed = ApiError(422, "validation_error", "Invalid.", [{"index": 0, "path": "x", "message": "m"}])
    assert detailed.envelope()["error"]["details"] == [{"index": 0, "path": "x", "message": "m"}]
