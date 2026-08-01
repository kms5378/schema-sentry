#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 \
  --set=pipeline_password="$SCHEMA_SENTRY_PIPELINE_PASSWORD" \
  --set=database_name="$PGDATABASE" <<'SQL'
SELECT format(
    'CREATE ROLE schema_sentry_pipeline NOINHERIT LOGIN PASSWORD %L',
    :'pipeline_password'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'schema_sentry_pipeline'
) \gexec
SELECT format(
    'ALTER ROLE schema_sentry_pipeline PASSWORD %L',
    :'pipeline_password'
) \gexec
GRANT CONNECT ON DATABASE :"database_name" TO schema_sentry_pipeline;
GRANT USAGE ON SCHEMA public, mart TO schema_sentry_pipeline;
GRANT SELECT ON TABLE public.purchases TO schema_sentry_pipeline;
GRANT SELECT, INSERT, UPDATE ON TABLE mart.daily_revenue TO schema_sentry_pipeline;
SQL
