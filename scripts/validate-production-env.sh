#!/usr/bin/env bash
set -uo pipefail

env_file=${1:-.env.production}
if [[ ! -f "$env_file" ]]; then
  echo "production env file not found: $env_file" >&2
  exit 1
fi

required=(
  SCHEMA_SENTRY_DOMAIN
  SCHEMA_SENTRY_DASHBOARD_BASE_URL
  SCHEMA_SENTRY_ADMIN_USER
  SCHEMA_SENTRY_ADMIN_HASH
  SCHEMA_SENTRY_API_KEY
  SOURCE_DB_ADMIN_PASSWORD
  SOURCE_DB_READER_PASSWORD
  SOURCE_DB_PIPELINE_PASSWORD
  METADATA_DB_PASSWORD
  AIRFLOW_DB_PASSWORD
  AIRFLOW_JWT_SECRET
)
invalid=0

read_value() {
  local key=$1
  local value
  value=$(awk -v target="$key" '
    index($0, target "=") == 1 { value = substr($0, length(target) + 2) }
    END { print value }
  ' "$env_file")
  value=${value%$'\r'}
  if [[ ${#value} -ge 2 ]]; then
    if [[ ${value:0:1} == "'" && ${value: -1} == "'" ]]; then
      value=${value:1:${#value}-2}
    elif [[ ${value:0:1} == '"' && ${value: -1} == '"' ]]; then
      value=${value:1:${#value}-2}
    fi
  fi
  printf '%s' "$value"
}

for key in "${required[@]}"; do
  value=$(read_value "$key")
  if [[ -z "$value" ]]; then
    echo "$key must be set for production" >&2
    invalid=1
    continue
  fi
  case "$value" in
    game_admin_dev|source_reader_dev|pipeline_writer_dev|schema_sentry_dev|airflow_dev|local-development-key|local-development-airflow-jwt-secret|replace-with-*|CHANGE_ME)
      echo "$key contains a development or placeholder value" >&2
      invalid=1
      ;;
  esac
done

dashboard_url=$(read_value SCHEMA_SENTRY_DASHBOARD_BASE_URL)
if [[ "$dashboard_url" != https://* ]]; then
  echo "SCHEMA_SENTRY_DASHBOARD_BASE_URL must use https" >&2
  invalid=1
fi

admin_hash=$(read_value SCHEMA_SENTRY_ADMIN_HASH)
if [[ "$admin_hash" != '$2'* ]]; then
  echo "SCHEMA_SENTRY_ADMIN_HASH must be a bcrypt hash" >&2
  invalid=1
fi

api_key=$(read_value SCHEMA_SENTRY_API_KEY)
if [[ ${#api_key} -lt 32 ]]; then
  echo "SCHEMA_SENTRY_API_KEY must be at least 32 characters" >&2
  invalid=1
fi

airflow_jwt=$(read_value AIRFLOW_JWT_SECRET)
if [[ ${#airflow_jwt} -lt 32 ]]; then
  echo "AIRFLOW_JWT_SECRET must be at least 32 characters" >&2
  invalid=1
fi

exit "$invalid"
