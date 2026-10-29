"""FastAPI application: payment batch endpoint, health checks and diagnostics."""

import os
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.db import Database
from app.errors import ApiError
from app.observability import RequestLogMiddleware, configure_logging
from app.request_parsing import MAX_BODY_BYTES, BatchRequestModel, parse_batch_request



class BatchResult(BaseModel):
    inserted_count: int
    skipped_count: int
    gross_outgoing_cents: int
    idempotency_mode: Literal["on", "off"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Diagnostics(BaseModel):
    instance_id: str
    idempotency_mode: Literal["on", "off"]


class Readiness(Diagnostics):
    status: Literal["ready"]


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in {
        400: "Malformed JSON, duplicate members, invalid encoding or empty body (`invalid_json`).",
        409: "A payment key already has a different amount in ON mode (`payment_amount_conflict`).",
        413: "Body exceeds 1 MiB (`request_too_large`).",
        415: "Missing or unsupported Content-Type (`unsupported_media_type`).",
        422: "`validation_error`, `unknown_firm`, `insufficient_funds` or `numeric_overflow`.",
        500: "Unexpected failure (`internal_error`).",
        503: "`temporarily_unavailable` (nothing applied) or `commit_outcome_unknown`.",
    }.items()
}

STATUS_CODES = {404: "not_found", 405: "method_not_allowed"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env(os.environ)
    configure_logging()
    database = Database(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await database.open()
        yield
        await database.close()

    app = FastAPI(
        title="TaxDome bulk firm payments",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        request.state.log["code"] = exc.code
        return JSONResponse(exc.envelope(), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, "http_error")
        error = ApiError(exc.status_code, code, str(exc.detail))
        return JSONResponse(error.envelope(), status_code=exc.status_code, headers=exc.headers)

    @app.post(
        "/payments/batch",
        status_code=201,
        response_model=BatchResult,
        responses=ERROR_RESPONSES,
        summary="Pay several firms from one payer's balance, all or nothing",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchRequest"}}},
            }
        },
    )
    async def create_batch(request: Request) -> JSONResponse:
        body = await read_limited_body(request)
        batch = parse_batch_request(body, request.headers.get("content-type"))
        result = await database.execute_batch(batch)
        result = {field: result[field] for field in BatchResult.model_fields}
        request.state.log.update(
            code="created",
            mode=result["idempotency_mode"],
            inserted=result["inserted_count"],
            skipped=result["skipped_count"],
        )
        return JSONResponse(result, status_code=201)

    @app.get("/health/live", summary="Process liveness; no database access")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get(
        "/health/ready",
        response_model=Readiness,
        responses={503: {"model": ErrorResponse}},
        summary="Database, function, privileges and mode are usable",
    )
    async def ready() -> dict[str, str]:
        mode = await database.check_ready()
        return {"status": "ready", "instance_id": settings.instance_id, "idempotency_mode": mode}

    @app.get(
        "/diagnostics",
        response_model=Diagnostics,
        responses={503: {"model": ErrorResponse}},
        summary="Instance identity and the database-derived idempotency mode",
    )
    async def diagnostics() -> dict[str, str]:
        mode = await database.check_ready()
        return {"instance_id": settings.instance_id, "idempotency_mode": mode}

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        request_schema = BatchRequestModel.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.update(request_schema.pop("$defs", {}))
        components["BatchRequest"] = request_schema
        app.openapi_schema = schema
        return schema

    app.openapi = openapi
    app.add_middleware(RequestLogMiddleware, instance_id=settings.instance_id)
    return app


async def read_limited_body(request: Request) -> bytes:
    """Read the body, stopping as soon as it exceeds the limit (also for chunked uploads)."""
    too_large = ApiError(413, "request_too_large", "Request body exceeds 1 MiB.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise too_large
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise too_large
    return bytes(body)


app = create_app() if os.environ.get("DATABASE_URL") else None
