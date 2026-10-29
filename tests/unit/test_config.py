import pytest

from app.config import Settings

BASE_ENV = {"INSTANCE_ID": "api-1", "DATABASE_URL": "postgresql://x"}


def test_defaults():
    settings = Settings.from_env(BASE_ENV)
    assert settings.instance_id == "api-1"
    assert settings.pool_min == 1
    assert settings.pool_max == 10
    assert settings.pool_timeout_s == 5.0
    assert settings.lock_timeout_ms == 5000
    assert settings.statement_timeout_ms == 15000


def test_overrides():
    settings = Settings.from_env(
        {**BASE_ENV, "DB_LOCK_TIMEOUT_MS": "2000", "DB_POOL_TIMEOUT_SECONDS": "1.5"}
    )
    assert settings.lock_timeout_ms == 2000
    assert settings.pool_timeout_s == 1.5


def test_missing_database_url_raises():
    with pytest.raises(ValueError):
        Settings.from_env({"INSTANCE_ID": "api-1"})
