"""Unexpected exceptions still produce the envelope, a correlation ID and a JSON log line."""

import asyncio
import json

import httpx

from app.config import Settings
from app.main import create_app


def test_unhandled_exception_returns_envelope_with_request_id(capsys):
    app = create_app(Settings(instance_id="api-test", database_url="postgresql://unused"))

    async def boom():
        raise RuntimeError("secret internals")

    app.add_api_route("/boom", boom)

    async def call():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/boom", headers={"X-Request-ID": "trace-500"})

    response = asyncio.run(call())
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Unexpected internal error."}}
    assert response.headers["x-request-id"] == "trace-500"
    assert "secret internals" not in response.text

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    completion = next(line for line in lines if line["msg"] == "request completed")
    assert (completion["status"], completion["code"], completion["request_id"]) == (500, "internal_error", "trace-500")
    assert any("RuntimeError" in line.get("exception", "") for line in lines)
