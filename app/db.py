"""Database access: connection pool, batch transaction ownership and error mapping."""

import json
from typing import Any

import psycopg
from psycopg import pq
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from app.config import Settings
from app.errors import ApiError
from app.request_parsing import BatchRequest

FUNCTION_SIGNATURE = "app.process_payment_batch(text,jsonb)"

# Business errors raised by the stored function with custom SQLSTATEs.
BUSINESS_ERRORS: dict[str, tuple[int, str, str]] = {
    "TD001": (422, "unknown_firm", "A payer or payee firm does not exist."),
    "TD002": (422, "insufficient_funds", "Payer balance cannot cover new outgoing payments."),
    "TD003": (422, "numeric_overflow", "A resulting balance would exceed the supported range."),
    "TD004": (409, "payment_amount_conflict", "A payment key already has a different amount."),
    "TD005": (422, "validation_error", "The payment batch is invalid."),
}

# Failures after which PostgreSQL is known to have rolled the transaction back.
TRANSIENT_SQLSTATES = {
    "TD006",  # missing or invalid mode configuration
    "55P03",  # lock_not_available (lock_timeout)
    "57014",  # query_canceled (statement_timeout)
    "40P01",  # deadlock_detected
    "40001",  # serialization_failure
}

UNAVAILABLE = (503, "temporarily_unavailable", "The service is temporarily unavailable; no changes were made.")


def _details(exc: Exception) -> list[dict[str, Any]] | None:
    diag = getattr(exc, "diag", None)
    raw = getattr(diag, "message_detail", None)
    if not raw:
        return None
    try:
        details = json.loads(raw)
    except ValueError:
        return None
    return details if isinstance(details, list) else None


def map_db_error(exc: Exception, during_commit: bool) -> ApiError:
    """Translate a database/pool failure into an API error without leaking internals."""
    if isinstance(exc, PoolTimeout):
        return ApiError(*UNAVAILABLE)
    if not isinstance(exc, psycopg.Error):
        return ApiError(500, "internal_error", "Unexpected internal error.")
    sqlstate = exc.sqlstate
    if sqlstate in BUSINESS_ERRORS:
        return ApiError(*BUSINESS_ERRORS[sqlstate], details=_details(exc))
    connection_failure = isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))
    if during_commit and connection_failure and sqlstate is None:
        # No answer from the server to COMMIT: the transaction may or may not have committed.
        return ApiError(
            503,
            "commit_outcome_unknown",
            "The database connection failed during commit; the payments may or may not be applied.",
        )
    if sqlstate in TRANSIENT_SQLSTATES or connection_failure:
        return ApiError(*UNAVAILABLE)
    return ApiError(500, "internal_error", "Unexpected internal error.")


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pool = AsyncConnectionPool(
            settings.database_url,
            min_size=settings.pool_min,
            max_size=settings.pool_max,
            timeout=settings.pool_timeout_s,
            kwargs={"autocommit": True},
            check=AsyncConnectionPool.check_connection,
            open=False,
        )

    async def open(self) -> None:
        # Do not block startup on the database; readiness reports its state.
        await self.pool.open(wait=False)

    async def close(self) -> None:
        await self.pool.close()

    async def execute_batch(self, request: BatchRequest) -> dict[str, Any]:
        """Run one batch as one READ COMMITTED transaction; return the function result after commit."""
        entries = json.dumps(
            [
                {
                    "payee_firm_uuid": p.payee_firm_uuid,
                    "amount_cents": p.amount_cents,
                    "description": p.description,
                }
                for p in request.payments
            ]
        )
        try:
            async with self.pool.connection() as conn:
                return await self._run_batch(conn, request.payer_firm_uuid, entries)
        except PoolTimeout as exc:
            raise map_db_error(exc, during_commit=False) from exc

    async def _run_batch(
        self, conn: psycopg.AsyncConnection, payer_uuid: str, entries: str
    ) -> dict[str, Any]:
        committing = False
        try:
            await conn.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            await conn.execute(
                "SELECT set_config('lock_timeout', %s, true), set_config('statement_timeout', %s, true)",
                (f"{self.settings.lock_timeout_ms}ms", f"{self.settings.statement_timeout_ms}ms"),
            )
            cursor = await conn.execute(
                "SELECT app.process_payment_batch(%s, %s::jsonb)", (payer_uuid, entries)
            )
            (result,) = await cursor.fetchone()
            committing = True
            await conn.execute("COMMIT")
            return result
        except Exception as exc:
            if not committing:
                await _rollback_quietly(conn)
            raise map_db_error(exc, during_commit=committing) from exc

    async def read_function_mode(self) -> str:
        """Effective mode from the exact function signature's stored configuration."""
        async with self.pool.connection(timeout=2) as conn:
            cursor = await conn.execute(
                "SELECT p.proconfig, has_function_privilege(p.oid, 'EXECUTE')"
                " FROM pg_catalog.pg_proc p WHERE p.oid = to_regprocedure(%s)",
                (FUNCTION_SIGNATURE,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise ApiError(503, "temporarily_unavailable", "Payment function is not installed.")
        config, can_execute = row
        if not can_execute:
            raise ApiError(503, "temporarily_unavailable", "Payment function is not executable.")
        modes = [s.partition("=")[2] for s in config or [] if s.startswith("app.payment_idempotency=")]
        if len(modes) != 1 or modes[0] not in ("on", "off"):
            raise ApiError(503, "temporarily_unavailable", "Payment idempotency mode is not configured.")
        return modes[0]

    async def check_ready(self) -> str:
        try:
            return await self.read_function_mode()
        except (psycopg.Error, PoolTimeout) as exc:
            raise ApiError(503, "temporarily_unavailable", "Database is unavailable.") from exc


async def _rollback_quietly(conn: psycopg.AsyncConnection) -> None:
    if conn.closed or conn.broken:
        return
    if conn.info.transaction_status == pq.TransactionStatus.IDLE:
        return
    try:
        await conn.execute("ROLLBACK")
    except psycopg.Error:
        pass  # the pool discards a connection it cannot reset
