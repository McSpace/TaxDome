"""HTTP contract: byte, media, JSON, shape and field validation end to end.

Every rejected request must leave balances and payments untouched.
"""

import json

import pytest

from tests.integration.support import (
    ABSENT_UUID,
    API_URLS,
    BATCH_PATH,
    error_code,
    post_batch,
    post_raw,
    snapshot,
)

MIB = 1_048_576


@pytest.fixture
def unchanged(base):
    before = snapshot()
    yield base
    assert snapshot() == before


def good_body(base, **overrides) -> dict:
    doc = {
        "payer_firm_uuid": base["A"].uuid,
        "payments": [{"amount": "10.00", "payee_firm_uuid": base["B"].uuid, "description": "ok"}],
    }
    doc.update(overrides)
    return doc


def raw(doc) -> bytes:
    return json.dumps(doc).encode()


@pytest.mark.case("REQ001", "REQ002", "REQ003", "REQ014", "REQ016")
@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   \n\t",
        b'{"payer_firm_uuid": "a", "payments": [',
        b'{"payer_firm_uuid": "a",}',
        b"{payer_firm_uuid: 1}",
        b'{"payer_firm_uuid": "unterminated}',
        b'{"payer_firm_uuid": "a" // line comment\n}',
        b'{"payer_firm_uuid": /* block */ "a"}',
        b"\xef\xbb\xbf{}",
        b'{"payer_firm_uuid": "\xff\xfe"}',
    ],
)
def test_invalid_json_is_400(http, unchanged, content):
    response = post_raw(http, content)
    assert response.status_code == 400
    assert error_code(response) == "invalid_json"


@pytest.mark.case("REQ014")
def test_duplicate_members_are_400(http, unchanged):
    payer, payee = unchanged["A"].uuid, unchanged["B"].uuid
    bodies = [
        f'{{"payer_firm_uuid": "{payer}", "payer_firm_uuid": "{payee}", "payments": []}}',
        f'{{"payer_firm_uuid": "{payer}", "payments": [], "payments": []}}',
        f'{{"payer_firm_uuid": "{payer}", "payments": [{{"amount": "1", "amount": "2", '
        f'"payee_firm_uuid": "{payee}", "description": "x"}}]}}',
        f'{{"payer_firm_uuid": "{payer}", "payments": [{{"amount": "1", "payee_firm_uuid": "{payee}", '
        f'"payee_firm_uuid": "{payer}", "description": "x"}}]}}',
    ]
    for body in bodies:
        response = post_raw(http, body.encode())
        assert (response.status_code, error_code(response)) == (400, "invalid_json")


@pytest.mark.case("REQ015", "REQ016")
@pytest.mark.parametrize(
    "content_type", [None, "text/plain", "application/x-www-form-urlencoded", "application/json; charset=iso-8859-1"]
)
def test_unsupported_media_type_is_415(http, unchanged, content_type):
    response = post_raw(http, raw(good_body(unchanged)), content_type)
    assert response.status_code == 415
    assert error_code(response) == "unsupported_media_type"


@pytest.mark.case("REQ015", "REQ016")
def test_json_with_utf8_charset_is_accepted(http, base):
    response = post_raw(http, raw(good_body(base)), "application/json; charset=utf-8")
    assert response.status_code == 201


@pytest.mark.case("REQ004", "REQ005", "REQ006", "REQ007", "REQ008", "REQ009", "REQ010",
                  "REQ011", "REQ012", "REQ013")
def test_shape_errors_are_422(http, unchanged):
    b = unchanged["B"].uuid
    entry = {"amount": "10.00", "payee_firm_uuid": b, "description": "ok"}
    docs = [None, [], "string", 1, True]
    docs += [{"payments": [entry]}, {"payer_firm_uuid": unchanged["A"].uuid}]
    docs += [good_body(unchanged, payments=v) for v in (None, {}, "x", 1, True, [])]
    docs += [good_body(unchanged, payments=[v]) for v in (None, "x", [], 1, True)]
    docs += [good_body(unchanged, payments=[entry, None, entry])]
    docs += [good_body(unchanged, payments=[{k: v for k, v in entry.items() if k != f}])
             for f in entry]
    docs += [good_body(unchanged, payer_firm_uuid=v) for v in (None, 1, True, [], {})]
    docs += [good_body(unchanged, payments=[{**entry, "payee_firm_uuid": v}]) for v in (None, 1, True, [], {})]
    docs += [good_body(unchanged, request_note="x"), good_body(unchanged, internal_id=1),
             good_body(unchanged, mode="off"), good_body(unchanged, a=1, b=2, mode="on")]
    docs += [good_body(unchanged, payments=[{**entry, extra: value}])
             for extra, value in (("currency", "USD"), ("amount_cents", 1000),
                                  ("payer_firm_id", 30), ("anything", None))]
    for doc in docs:
        response = post_raw(http, raw(doc))
        assert response.status_code == 422, doc
        assert error_code(response) == "validation_error"


@pytest.mark.case("AMT006", "AMT007", "AMT008", "AMT009", "AMT010", "AMT011", "AMT012",
                  "AMT014", "AMT015", "AMT016", "AMT018", "OPS004")
@pytest.mark.parametrize(
    "amount",
    [
        "0", "0.0", "0.00", "000.00", "-1", "-0.01", "-0.00",
        "1.001", "1.999", "0.0001", "1.2300", "1e2", "1E+2", "1e-2",
        "1,25", "1,000.00", "1 000.00", "$1.00", "€1.00",
        "+1.00", " 1.00", "1.00 ", "\t1.00", "1.00\n", ".50", "1.", ".", "", "   ",
        "١٠", "１０", "−10", "NaN", "Infinity", "-Infinity", "null", "one",
        1, 1.25, True, None, [], {},
        "21474836.48", "9" * 40, "9" * 5000, "0" * 5000 + "1",
    ],
)
def test_invalid_amounts_are_422(http, unchanged, amount):
    doc = good_body(unchanged)
    doc["payments"][0]["amount"] = amount
    response = post_raw(http, raw(doc))
    assert response.status_code == 422
    assert error_code(response) == "validation_error"


@pytest.mark.case("FRM004", "FRM006", "FRM007")
@pytest.mark.parametrize("field", ["payer", "payee"])
def test_malformed_uuids_are_422(http, unchanged, field):
    good = unchanged["A"].uuid
    variants = [good[:-1], good[:8], good.replace("a", "g"), "not-a-uuid", "{" + good + "}",
                "urn:uuid:" + good, good.replace("-", ""), " " + good, good + " ", "\t" + good,
                good + "\n", "\n" + good, "30", "10", "1"]
    for value in variants:
        doc = good_body(unchanged)
        if field == "payer":
            doc["payer_firm_uuid"] = value
        else:
            doc["payments"][0]["payee_firm_uuid"] = value
        response = post_raw(http, raw(doc))
        assert (response.status_code, error_code(response)) == (422, "validation_error"), value


@pytest.mark.case("TXT003")
@pytest.mark.parametrize("description", [None, 1, True, [], {}])
def test_nonstring_description_is_422(http, unchanged, description):
    doc = good_body(unchanged)
    doc["payments"][0]["description"] = description
    assert post_raw(http, raw(doc)).status_code == 422


@pytest.mark.case("TXT006")
def test_escaped_characters_are_stored_exactly(http, base):
    descriptions = ['say "hi"', "back\\slash", "line\nbreak", "tab\tstop", "cr\rlf", "\u0001\u001f"]
    response = post_batch(http, base["A"], [(base["B"], "0.01", d) for d in descriptions])
    assert response.status_code == 201
    assert [row[4] for row in snapshot().payments] == descriptions


@pytest.mark.case("TXT006")
def test_null_character_is_rejected(http, unchanged):
    response = post_batch(http, unchanged["A"], [(unchanged["B"], "1", "nul\u0000here")])
    assert (response.status_code, error_code(response)) == (422, "validation_error")


def test_lone_surrogate_is_rejected(http, unchanged):
    body = (
        f'{{"payer_firm_uuid": "{unchanged["A"].uuid}", "payments": [{{"amount": "1", '
        f'"payee_firm_uuid": "{unchanged["B"].uuid}", "description": "\\ud800"}}]}}'
    )
    response = post_raw(http, body.encode())
    assert (response.status_code, error_code(response)) == (422, "validation_error")


@pytest.mark.case("BAT003", "BAT004", "BAT012")
@pytest.mark.parametrize("bad_position", [0, 1, 2])
def test_one_bad_entry_rejects_batch(http, unchanged, bad_position):
    b, c = unchanged["B"].uuid, unchanged["C"].uuid
    bad_entries = [
        {"amount": "1.001", "payee_firm_uuid": b, "description": "bad amount"},
        {"amount": "1.00", "payee_firm_uuid": b},
    ]
    for bad in bad_entries:
        payments = [
            {"amount": "1.00", "payee_firm_uuid": b, "description": "first"},
            {"amount": "1.00", "payee_firm_uuid": c, "description": "second"},
        ]
        payments.insert(bad_position, bad)
        response = post_raw(http, raw(good_body(unchanged, payments=payments)))
        assert (response.status_code, error_code(response)) == (422, "validation_error")
        assert [d["index"] for d in response.json()["error"]["details"]] == [bad_position]


@pytest.mark.case("BAT012")
def test_several_problems_reported_in_order(http, unchanged):
    b = unchanged["B"].uuid
    payments = [
        {"amount": "1.00", "payee_firm_uuid": ABSENT_UUID, "description": "unknown payee"},
        {"amount": "1.001", "payee_firm_uuid": b, "description": "bad amount"},
        {"amount": "1.00", "payee_firm_uuid": b, "description": "fine"},
        {"amount": "1.00", "payee_firm_uuid": b},
    ]
    response = post_raw(http, raw(good_body(unchanged, payments=payments)))
    assert (response.status_code, error_code(response)) == (422, "validation_error")
    assert [d["index"] for d in response.json()["error"]["details"]] == [1, 3]

    payments = [payments[0], payments[2]]
    response = post_raw(http, raw(good_body(unchanged, payments=payments)))
    assert (response.status_code, error_code(response)) == (422, "unknown_firm")
    assert response.json()["error"]["details"] == [{"index": 0, "path": "payments[0].payee_firm_uuid"}]


@pytest.mark.case("REQ018")
def test_field_order_and_whitespace_do_not_matter(http, base):
    a, b = base["A"].uuid, base["B"].uuid
    compact = f'{{"payer_firm_uuid":"{a}","payments":[{{"amount":"1","payee_firm_uuid":"{b}","description":"x1"}}]}}'
    pretty = (
        f'{{\n  "payments": [\n    {{\n      "description": "x2",\n      "payee_firm_uuid": "{b}",\n'
        f'      "amount": "1"\n    }}\n  ],\n  "payer_firm_uuid": "{a}"\n}}\n'
    )
    for body in (compact, pretty):
        response = post_raw(http, body.encode())
        assert response.status_code == 201
        assert response.json()["inserted_count"] == 1


@pytest.mark.case("OPS001")
@pytest.mark.parametrize("count, status", [(999, 201), (1000, 201), (1001, 422)])
def test_batch_size_limit(http, base, count, status):
    entries = [(base["B"], "0.01", f"entry {i}") for i in range(count)]
    before = snapshot()
    response = post_batch(http, base["A"], entries)
    assert response.status_code == status
    if status == 201:
        assert response.json()["inserted_count"] == count
        assert len(snapshot().payments) == count
    else:
        assert snapshot() == before


@pytest.mark.case("OPS003")
@pytest.mark.parametrize("unit", ["x", "é", "😀"])
@pytest.mark.parametrize("length, status", [(1023, 201), (1024, 201), (1025, 422)])
def test_description_length_limit(http, base, unit, length, status):
    response = post_batch(http, base["A"], [(base["B"], "1", unit * length)])
    assert response.status_code == status
    if status == 201:
        assert snapshot().payments[0][4] == unit * length


def padded_body(base, size: int) -> bytes:
    """A valid two-entry body padded to exactly `size` bytes via the descriptions."""
    def build(pad: int) -> bytes:
        return raw(good_body(base, payments=[
            {"amount": "1", "payee_firm_uuid": base["B"].uuid, "description": "p" * 1000},
            {"amount": "1", "payee_firm_uuid": base["C"].uuid, "description": "q"},
        ])) + b" " * pad

    return build(size - len(build(0)))


@pytest.mark.case("OPS002")
@pytest.mark.parametrize("size, status", [(MIB - 1, 201), (MIB, 201), (MIB + 1, 413)])
def test_body_size_limit(http, base, size, status):
    content = padded_body(base, size)
    assert len(content) == size
    response = post_raw(http, content)
    assert response.status_code == status
    if status == 413:
        assert error_code(response) == "request_too_large"


@pytest.mark.case("OPS002")
@pytest.mark.parametrize("target", ["nginx", *API_URLS])
def test_chunked_body_over_limit_is_413(http, apis, unchanged, target):
    """Without Content-Length the limit must hold while streaming, at Nginx and at each API."""
    client = http if target == "nginx" else apis[target]

    def chunks():
        yield b'{"payer_firm_uuid": "' + unchanged["A"].uuid.encode() + b'", "pad": "'
        for _ in range(17):
            yield b"x" * 65536
        yield b'"}'

    response = client.post(BATCH_PATH, content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert error_code(response) == "request_too_large"


def test_unknown_route_and_method(http):
    missing = http.get("/nope")
    assert (missing.status_code, error_code(missing)) == (404, "not_found")
    wrong = http.get(BATCH_PATH)
    assert (wrong.status_code, error_code(wrong)) == (405, "method_not_allowed")


def test_openapi_documents_contract(http):
    spec = http.get("/openapi.json").json()
    assert {"/payments/batch", "/health/live", "/health/ready", "/diagnostics"} <= set(spec["paths"])
    body = spec["paths"]["/payments/batch"]["post"]["requestBody"]["content"]["application/json"]
    assert body["schema"]["$ref"] == "#/components/schemas/BatchRequest"
    assert "PaymentRequestEntry" in spec["components"]["schemas"]
