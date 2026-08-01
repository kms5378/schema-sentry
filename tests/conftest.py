import os

os.environ.setdefault(
    "SCHEMA_SENTRY_METADATA_DATABASE_URL",
    "postgresql+psycopg://schema_sentry:schema_sentry_dev@localhost:55433/schema_sentry",
)
os.environ.setdefault(
    "SCHEMA_SENTRY_SOURCE_DATABASE_URL",
    "postgresql+psycopg://schema_sentry_reader:source_reader_dev@localhost:55432/game_source",
)
os.environ.setdefault("SCHEMA_SENTRY_API_KEY", "test-api-key")
