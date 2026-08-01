import pytest


def test_production_rejects_disabled_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEMA_SENTRY_ENVIRONMENT", "production")
    monkeypatch.setenv("SCHEMA_SENTRY_AUTH_DISABLED", "true")
    monkeypatch.setenv(
        "SCHEMA_SENTRY_METADATA_DATABASE_URL",
        "postgresql+psycopg://metadata:secret@metadata-db/schema_sentry",
    )
    monkeypatch.setenv(
        "SCHEMA_SENTRY_SOURCE_DATABASE_URL",
        "postgresql+psycopg://reader:secret@source-db/game_source",
    )
    monkeypatch.setenv("SCHEMA_SENTRY_API_KEY", "test-api-key")

    from schema_sentry.config import Settings

    with pytest.raises(ValueError, match="AUTH_DISABLED"):
        Settings()
