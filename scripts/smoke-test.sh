#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
env_file=${SCHEMA_SENTRY_ENV_FILE:-"$project_dir/.env.production"}
base_url=${SCHEMA_SENTRY_BASE_URL:?set SCHEMA_SENTRY_BASE_URL, for example https://schema.example.com}
admin_user=${SCHEMA_SENTRY_ADMIN_USER:?set SCHEMA_SENTRY_ADMIN_USER}
compose=(docker compose --env-file "$env_file" -f "$project_dir/docker-compose.yml" -f "$project_dir/docker-compose.prod.yml")

if [[ ! -f "$env_file" ]]; then
  echo "production env file not found: $env_file" >&2
  exit 1
fi

"$project_dir/scripts/validate-production-env.sh" "$env_file"

if [[ -n "${SCHEMA_SENTRY_SMOKE_PASSWORD:-}" ]]; then
  admin_password=$SCHEMA_SENTRY_SMOKE_PASSWORD
else
  read -r -s -p "Caddy Basic Auth password: " admin_password </dev/tty
  echo >&2
fi

authenticated_get() {
  local url=$1
  local curl_credentials="$admin_user:$admin_password"
  curl_credentials=${curl_credentials//\\/\\\\}
  curl_credentials=${curl_credentials//\"/\\\"}
  printf 'user = "%s"\n' "$curl_credentials" |
    curl --config - --fail --silent --show-error --max-time 10 --output /dev/null --url "$url"
}

authenticated_get "${base_url%/}/health/live"
echo "caddy liveness: ok"

authenticated_get "${base_url%/}/health/ready"
echo "api readiness: ok"

"${compose[@]}" exec -T api .venv/bin/alembic current --check-heads >/dev/null
echo "metadata migration: ok"

"${compose[@]}" exec -T airflow-api-server \
  curl --fail --silent --show-error --max-time 10 \
  http://localhost:8080/api/v2/monitor/health >/dev/null
echo "airflow health: ok"
