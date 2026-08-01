import os

os.environ.setdefault(
    "SCHEMA_SENTRY_METADATA_DATABASE_URL",
    "postgresql+psycopg://metadata:secret@metadata-db/schema_sentry",
)
os.environ.setdefault(
    "SCHEMA_SENTRY_SOURCE_DATABASE_URL",
    "postgresql+psycopg://reader:secret@source-db/game_source",
)
os.environ.setdefault("SCHEMA_SENTRY_API_KEY", "test-api-key")
