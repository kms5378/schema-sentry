#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=reader_password="$SCHEMA_SENTRY_SOURCE_READER_PASSWORD" \
  --set=database_name="$POSTGRES_DB" <<'SQL'
CREATE ROLE schema_sentry_reader NOINHERIT LOGIN PASSWORD :'reader_password';
GRANT CONNECT ON DATABASE :"database_name" TO schema_sentry_reader;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS mart;
REVOKE CREATE ON SCHEMA mart FROM PUBLIC;
GRANT USAGE ON SCHEMA public, mart TO schema_sentry_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public, mart
    GRANT SELECT ON TABLES TO schema_sentry_reader;
SQL
