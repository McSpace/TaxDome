"""Runtime settings for an API instance, read from environment variables."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    instance_id: str
    database_url: str
    pool_min: int = 1
    pool_max: int = 10
    pool_timeout_s: float = 5.0
    lock_timeout_ms: int = 5000
    statement_timeout_ms: int = 15000

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        database_url = env.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        return cls(
            instance_id=env.get("INSTANCE_ID", "api-local"),
            database_url=database_url,
            pool_min=int(env.get("DB_POOL_MIN", cls.pool_min)),
            pool_max=int(env.get("DB_POOL_MAX", cls.pool_max)),
            pool_timeout_s=float(env.get("DB_POOL_TIMEOUT_SECONDS", cls.pool_timeout_s)),
            lock_timeout_ms=int(env.get("DB_LOCK_TIMEOUT_MS", cls.lock_timeout_ms)),
            statement_timeout_ms=int(
                env.get("DB_STATEMENT_TIMEOUT_MS", cls.statement_timeout_ms)
            ),
        )
