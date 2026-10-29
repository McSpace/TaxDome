"""Structured request-completion logging with correlation IDs."""

import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

logger = logging.getLogger("taxdome.requests")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("taxdome")
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False


class RequestLogMiddleware:
    """Assigns a correlation ID and logs one line per request.

    Endpoints add outcome fields (error code, counts, mode) to scope["state"]["log"].
    Descriptions and request bodies are never logged.
    """

    def __init__(self, app: ASGIApp, instance_id: str) -> None:
        self.app = app
        self.instance_id = instance_id

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        fields: dict = {}
        scope.setdefault("state", {})["log"] = fields
        scope["state"]["request_id"] = request_id
        status = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (REQUEST_ID_HEADER.encode(), request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "request completed",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "instance": self.instance_id,
                        "method": scope["method"],
                        "path": scope["path"],
                        "status": status,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                        **fields,
                    }
                },
            )
