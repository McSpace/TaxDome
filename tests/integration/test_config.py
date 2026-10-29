"""Deployment configuration: mode agreement, instance identity, sample walkthrough, proxy."""

import json
from pathlib import Path

import httpx
import psycopg
import pytest

from tests.integration.support import (
    API_URLS,
    SAMPLE_FIXTURE,
    error_code,
    post_batch,
    post_raw,
    preflight,
    reset_db,
    snapshot,
)

OPPOSITE = {"on": "off", "off": "on"}
SAMPLE = Path("examples/sample.json")
INTRO = Path("examples/intro.json")
NGINX_CONF = Path("nginx/nginx.conf")


@pytest.mark.case("CFG001")
def test_deployment_mode(mode, http):
    assert http.get("/diagnostics").json()["idempotency_mode"] == mode


@pytest.mark.case("CFG003")
def test_preflight_passes(mode):
    assert preflight(mode) == []


@pytest.mark.case("CFG003")
def test_instances_report_identity_and_mode(apis, mode):
    for name, client in apis.items():
        assert client.get("/diagnostics").json() == {"instance_id": name, "idempotency_mode": mode}
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["instance_id"] == name
        assert client.get("/health/live").json() == {"status": "live"}


def test_nginx_round_robins_across_all_instances(http):
    seen = {http.get("/diagnostics").json()["instance_id"] for _ in range(9)}
    assert seen == set(API_URLS)


@pytest.mark.case("CFG002")
def test_preflight_detects_mismatch(mode):
    problems = "\n".join(preflight(OPPOSITE[mode]))
    for name in ("database", *API_URLS, "nginx"):
        assert name in problems


@pytest.mark.case("BAS005")
def test_sample_through_nginx(admin, http):
    reset_db(admin, SAMPLE_FIXTURE)
    response = post_raw(http, SAMPLE.read_bytes())
    assert response.status_code == 201
    assert response.json() == {
        "inserted_count": 3,
        "skipped_count": 0,
        "gross_outgoing_cents": 1325125,
        "idempotency_mode": response.json()["idempotency_mode"],
    }
    after = snapshot()
    assert after.balances == {1: 3674875, 2: 170075, 3: 1405050}
    assert after.total == 5250000
    assert after.rows_without_ids() == [
        (1, 3, 625000, "Overflow returns, August 2026"),
        (1, 3, 580050, "Amended returns, August 2026"),
        (1, 2, 120075, "Bookkeeping cleanup, 3 clients"),
    ]


@pytest.mark.case("BAS016")
def test_intro_example(admin, http):
    reset_db(admin, SAMPLE_FIXTURE)
    response = post_raw(http, INTRO.read_bytes())
    assert response.status_code == 201
    assert response.json()["gross_outgoing_cents"] == 150075
    assert snapshot().balances == {1: 4849925, 2: 170075, 3: 230000}


def test_nginx_does_not_replay_post():
    conf = NGINX_CONF.read_text()
    assert "proxy_next_upstream error timeout;" in conf
    assert "non_idempotent" not in conf


@pytest.mark.case("OPS002")
def test_nginx_rejects_large_body_with_json(http):
    response = post_raw(http, b" " * (1_048_576 + 1))
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/json")
    assert error_code(response) == "request_too_large"


def test_request_id_is_returned(http):
    response = http.get("/health/live", headers={"X-Request-ID": "trace-123"})
    assert response.headers["x-request-id"] == "trace-123"


@pytest.mark.case("CFG003")
def test_ready_fails_without_mode(admin, apis, base, mode):
    """Missing function configuration makes every instance unready and refuses payments."""
    admin.execute("ALTER FUNCTION app.process_payment_batch(text, jsonb) RESET app.payment_idempotency")
    try:
        for client in apis.values():
            assert client.get("/health/ready").status_code == 503
            assert client.get("/diagnostics").status_code == 503
            response = post_batch(client, base["A"], [(base["B"], "1", "no mode")])
            assert (response.status_code, error_code(response)) == (503, "temporarily_unavailable")
        assert snapshot().payments == []
    finally:
        admin.execute(
            psycopg.sql.SQL(
                "ALTER FUNCTION app.process_payment_batch(text, jsonb) SET app.payment_idempotency = {}"
            ).format(psycopg.sql.Literal(mode))
        )
    for client in apis.values():
        assert client.get("/health/ready").status_code == 200
