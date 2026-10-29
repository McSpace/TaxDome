import os

import httpx
import psycopg
import pytest

from tests.integration.support import (
    API_URLS,
    BASE_FIXTURE,
    BASE_URL,
    admin_connect,
    clear_hooks,
    preflight,
    reset_db,
)

EXPECTED_MODE = os.environ.get("EXPECTED_IDEMPOTENCY_MODE", "on")


@pytest.fixture(scope="session")
def mode() -> str:
    return EXPECTED_MODE


@pytest.fixture(scope="session", autouse=True)
def _verify_deployment_mode():
    """Abort before any payment test unless every component reports the expected mode."""
    problems = preflight(EXPECTED_MODE)
    if problems:
        pytest.exit("Deployment preflight failed:\n  " + "\n  ".join(problems), returncode=3)


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


@pytest.fixture(scope="session")
def http():
    """Client for the public entry point (Nginx in the full stack)."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        yield client


@pytest.fixture(scope="session")
def apis():
    """Direct clients for each API instance, keyed by instance id."""
    clients = {name: httpx.Client(base_url=url, timeout=30) for name, url in API_URLS.items()}
    yield clients
    for client in clients.values():
        client.close()
