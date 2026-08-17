from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr
from sqlalchemy import text

from app.config import Settings
from app.db.session import build_engine


def test_database_url_is_redacted_in_settings() -> None:
    database_url = "postgresql+psycopg://month3:database-secret@postgres/month3"
    configured = Settings(
        _env_file=None,
        database_url=database_url,
    )

    assert isinstance(configured.database_url, SecretStr)
    assert configured.database_url.get_secret_value() == database_url
    assert "database-secret" not in repr(configured)
    assert "database-secret" not in str(configured.model_dump())


def test_build_engine_supports_sqlite_for_unit_tests() -> None:
    engine = build_engine("sqlite://")

    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_build_engine_supports_psycopg_without_connecting() -> None:
    engine = build_engine("postgresql+psycopg://month3:database-secret@postgres/month3")

    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "postgres"
        assert engine.url.database == "month3"
    finally:
        engine.dispose()


def test_build_engine_rejects_empty_database_url() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL must not be empty"):
        build_engine("   ")


def test_compose_connects_api_and_worker_to_postgres() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["postgres"]["image"] == "postgres:17-alpine"
    assert "ports" not in services["postgres"]
    assert services["postgres"]["volumes"] == ["postgres_data:/var/lib/postgresql/data"]

    for service_name in ("api", "worker"):
        database_url = services[service_name]["environment"]["DATABASE_URL"]
        assert database_url.startswith("postgresql+psycopg://")
        assert "@postgres:5432/" in database_url
        assert (
            services[service_name]["depends_on"]["postgres"]["condition"]
            == "service_healthy"
        )
