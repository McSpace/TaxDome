"""Static checks of the proxy configuration's retry and keep-alive rules."""

import re
from pathlib import Path

CONF = (Path(__file__).resolve().parents[2] / "nginx" / "nginx.conf").read_text()
UVICORN_KEEP_ALIVE_SECONDS = 5  # uvicorn's default --timeout-keep-alive


def test_post_is_never_replayed_but_refused_connections_fail_over():
    # Without "non_idempotent", nginx passes a POST to another server only if nothing was sent
    # to the first one, so failover cannot apply a payment twice.
    assert re.search(r"proxy_next_upstream\s+error\s+timeout;", CONF)
    assert "non_idempotent" not in CONF
    assert "proxy_next_upstream off" not in CONF


def test_upstream_keepalive_closes_before_uvicorn_does():
    match = re.search(r"keepalive_timeout\s+(\d+)s;", CONF.split("upstream api", 1)[1].split("}", 1)[0])
    assert match and int(match.group(1)) < UVICORN_KEEP_ALIVE_SECONDS
