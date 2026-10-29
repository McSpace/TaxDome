import os

import psycopg
import pytest

from tests.integration.support import BASE_FIXTURE, admin_connect, clear_hooks, reset_db

EXPECTED_MODE = os.environ.get("EXPECTED_IDEMPOTENCY_MODE", "on")


@pytest.fixture(scope="session")
def mode() -> str:
    return EXPECTED_MODE


@pytest.fixture
def admin():
    with admin_connect() as conn:
        yield conn
        clear_hooks(conn)


@pytest.fixture
def base(admin: psycopg.Connection) -> dict:
    reset_db(admin, BASE_FIXTURE)
    return {f.alias: f for f in BASE_FIXTURE}


@pytest.fixture(autouse=True)
def _case_properties(request, record_property, mode):
    ids = [case_id for marker in request.node.iter_markers("case") for case_id in marker.args]
    if ids:
        record_property("case_ids", ",".join(ids))
    record_property("idempotency_mode", mode)
