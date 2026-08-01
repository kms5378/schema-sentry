#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"

compose=(docker compose -p schema-sentry-demo -f docker-compose.yml -f docker-compose.demo.yml)
api_key=""
api_url=http://127.0.0.1:8100
mailpit_url=http://127.0.0.1:8125
restore_sql="$project_dir/demo/sql/011_restore_schema.sql"

json_field() {
  local field=$1
  "${compose[@]}" exec -T api .venv/bin/python -c \
    'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' "$field"
}

json_change_count() {
  "${compose[@]}" exec -T api .venv/bin/python -c \
    'import json, sys; print(len(json.load(sys.stdin)["changes"]))'
}

api_post() {
  local path=$1
  local body=$2
  curl --fail --silent --show-error --max-time 15 \
    -H "X-API-Key: $api_key" \
    -H "Content-Type: application/json" \
    --data "$body" \
    "$api_url$path"
}

restore_schema() {
  "${compose[@]}" exec -T source-db \
    psql -v ON_ERROR_STOP=1 -U game_admin -d game_source_demo \
    < "$restore_sql" >/dev/null 2>&1 || true
}
trap restore_schema EXIT

"${compose[@]}" up -d source-db metadata-db mailpit >/dev/null
"${compose[@]}" run --rm api .venv/bin/alembic upgrade head >/dev/null
restore_schema
"${compose[@]}" exec -T metadata-db \
  psql -v ON_ERROR_STOP=1 -U schema_sentry -d schema_sentry_demo <<'SQL' >/dev/null
DELETE FROM data_sources WHERE key = 'game';
DELETE FROM pipelines WHERE key = 'daily_revenue';
INSERT INTO data_sources (id, key, display_name, connection_ref, enabled, baseline_version, created_at)
VALUES (gen_random_uuid(), 'game', 'Game database', 'SCHEMA_SENTRY_SOURCE_DATABASE_URL', true, 1, now());
SQL
curl --fail --silent --show-error --request DELETE "$mailpit_url/api/v1/messages" >/dev/null
"${compose[@]}" up -d --build api >/dev/null
curl --retry 20 --retry-delay 1 --retry-all-errors --fail --silent --show-error \
  "$api_url/health/ready" >/dev/null
api_key=$("${compose[@]}" exec -T api printenv SCHEMA_SENTRY_API_KEY)

baseline=$(api_post "/api/v1/scans" '{"source_key":"game"}')
baseline_id=$(printf '%s' "$baseline" | json_field scan_id)
[[ $(printf '%s' "$baseline" | json_change_count) == 0 ]]
echo "baseline scan: completed ($baseline_id)"

"${compose[@]}" run --rm api .venv/bin/schema-sentry catalog sync /app/catalog.yaml >/dev/null
"${compose[@]}" exec -T source-db \
  psql -v ON_ERROR_STOP=1 -U game_admin -d game_source_demo \
  < "$project_dir/demo/sql/010_breaking_change.sql" >/dev/null

broken=$(api_post "/api/v1/scans" '{"source_key":"game"}')
broken_id=$(printf '%s' "$broken" | json_field scan_id)
[[ $(printf '%s' "$broken" | json_change_count) == 1 ]]
echo "breaking drift: detected ($broken_id)"

latest=$(curl --fail --silent --show-error "$api_url/api/v1/scans/latest")
printf '%s' "$latest" | "${compose[@]}" exec -T api .venv/bin/python -c '
import json, sys
data = json.load(sys.stdin)
assert data["changes"][0]["severity"] == "BREAKING"
assert "daily_revenue" in data["changes"][0]["affected_dags"]
'
echo "affected DAG: daily_revenue"

blocked_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -X POST -H "X-API-Key: $api_key" \
  "$api_url/api/v1/pipelines/daily_revenue/validate")
[[ "$blocked_status" == 409 ]]
echo "pipeline validation: blocked"

for attempt in {1..20}; do
  persisted=$(curl --fail --silent --show-error "$api_url/api/v1/scans/$broken_id")
  delivery_sent=$(printf '%s' "$persisted" | "${compose[@]}" exec -T api \
    .venv/bin/python -c '
import json, sys
data = json.load(sys.stdin)
print(any(item["channel"] == "EMAIL" and item["status"] == "SENT" for item in data["deliveries"]))
')
  messages=$(curl --fail --silent --show-error "$mailpit_url/api/v1/messages")
  message_matches=$(printf '%s' "$messages" | "${compose[@]}" exec -T api \
    .venv/bin/python -c '
import json, sys
scan_id = sys.argv[1]
data = json.load(sys.stdin)
print(any(scan_id in item["Snippet"] for item in data["messages"]))
' "$broken_id")
  if [[ "$delivery_sent" == True && "$message_matches" == True ]]; then
    break
  fi
  [[ "$attempt" -lt 20 ]]
  sleep 1
done
echo "email notification: sent"

restore_schema
restored=$(api_post "/api/v1/scans" '{"source_key":"game"}')
restored_id=$(printf '%s' "$restored" | json_field scan_id)
latest=$(curl --fail --silent --show-error "$api_url/api/v1/scans/latest")
[[ $(printf '%s' "$latest" | json_change_count) == 0 ]]
echo "restoration scan: resolved ($restored_id)"

safe_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -X POST -H "X-API-Key: $api_key" \
  "$api_url/api/v1/pipelines/daily_revenue/validate")
[[ "$safe_status" == 200 ]]
echo "pipeline validation: safe"
echo "dashboard: $api_url/"
echo "email inbox: $mailpit_url/"
