"""Idempotent database initializer, run by the one-shot db-init service.

It creates roles, schema, function, privileges and the seed in one transaction,
and embeds the deployment's idempotency mode in the function's configuration.
Re-running it on an existing database never touches balances or payments, and it
refuses to relabel a database that was initialized with a different mode.
"""

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

VALID_MODES = ("on", "off")
FUNCTION_SIGNATURE = "app.process_payment_batch(text,jsonb)"
LOCK_KEY = 7_401_123  # serializes concurrent initializers
DEFAULT_SQL_DIR = Path(__file__).resolve().parent.parent / "db"

EXIT_INVALID_MODE = 2
EXIT_MODE_MISMATCH = 3


class MigrationError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def validate_mode(mode: str | None) -> str:
    if mode is None:
        return "on"
    if mode not in VALID_MODES:
        raise MigrationError(
            f"PAYMENT_IDEMPOTENCY_MODE must be exactly 'on' or 'off', got {mode!r}",
            EXIT_INVALID_MODE,
        )
    return mode


def installed_mode(conn: psycopg.Connection) -> tuple[bool, str | None]:
    """Return (function exists, mode from its configuration or None)."""
    row = conn.execute(
        "SELECT p.proconfig FROM pg_catalog.pg_proc p WHERE p.oid = to_regprocedure(%s)",
        (FUNCTION_SIGNATURE,),
    ).fetchone()
    if row is None:
        return False, None
    for setting in row[0] or []:
        name, _, value = setting.partition("=")
        if name == "app.payment_idempotency":
            return True, value
    return True, None


def _ensure_role(conn: psycopg.Connection, name: str, login: bool) -> None:
    exists = conn.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (name,)).fetchone()
    if not exists:
        conn.execute(
            sql.SQL("CREATE ROLE {} {}").format(
                sql.Identifier(name), sql.SQL("LOGIN" if login else "NOLOGIN")
            )
        )


def migrate(admin_url: str, mode: str | None, api_password: str, sql_dir: Path | None = None) -> str:
    """Initialize or verify the database; return the effective mode."""
    mode = validate_mode(mode)
    if not api_password:
        raise MigrationError("API_DB_PASSWORD is required")
    sql_dir = sql_dir or Path(os.environ.get("DB_SQL_DIR", DEFAULT_SQL_DIR))

    with psycopg.connect(admin_url) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))

        exists, current = installed_mode(conn)
        if exists and current != mode:
            raise MigrationError(
                f"database is initialized with idempotency mode {current!r}, "
                f"but {mode!r} was requested; use a fresh database to change mode",
                EXIT_MODE_MISMATCH,
            )

        _ensure_role(conn, "payments_owner", login=False)
        _ensure_role(conn, "payments_api", login=True)
        conn.execute(
            sql.SQL("ALTER ROLE payments_api WITH LOGIN PASSWORD {}").format(sql.Literal(api_password))
        )
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        conn.execute("CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION payments_owner")

        # Objects are created by their owner, so SECURITY DEFINER runs as a non-superuser.
        conn.execute("SET LOCAL ROLE payments_owner")
        for path in sorted(sql_dir.glob("*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
        conn.execute("RESET ROLE")
        # Setting a custom parameter in a function's configuration requires a superuser.
        conn.execute(
            sql.SQL(
                "ALTER FUNCTION app.process_payment_batch(text, jsonb) SET app.payment_idempotency = {}"
            ).format(sql.Literal(mode))
        )
    return mode


def main() -> int:
    try:
        mode = migrate(
            os.environ["ADMIN_DATABASE_URL"],
            os.environ.get("PAYMENT_IDEMPOTENCY_MODE"),
            os.environ.get("API_DB_PASSWORD", ""),
        )
    except MigrationError as exc:
        print(f"db-init: {exc}", file=sys.stderr)
        return exc.exit_code
    print(f"db-init: database ready, idempotency mode {mode!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
