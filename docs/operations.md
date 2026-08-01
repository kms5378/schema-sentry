# Schema Sentry Mini PC Operations

This runbook deploys Schema Sentry on one Linux mini PC with Docker Compose. Only Caddy publishes host ports; PostgreSQL, FastAPI, Mailpit, and Airflow stay on the private Compose network.

## Prerequisites

- A domain whose A/AAAA record points to the mini PC
- Router/firewall forwarding TCP 80 and 443 only
- Docker Engine with Compose 2.24.4 or newer (`!reset` is used by the production overlay)
- A clone of this repository on an encrypted local disk

## Create production secrets

Copy the example without committing the result:

```bash
cp .env.example .env.production
chmod 600 .env.production
```

Generate the API secret, Airflow JWT secret, and each database password as URL-safe values. Run the command once per credential and never reuse an output:

```bash
openssl rand -hex 32
```

Generate the Caddy password hash interactively so the plaintext password is never a command argument:

```bash
docker run --rm -it caddy:2.11.4-alpine caddy hash-password
```

Set strong, distinct database passwords and these production values in `.env.production`:

```dotenv
SCHEMA_SENTRY_ENVIRONMENT=production
SCHEMA_SENTRY_AUTH_DISABLED=false
SCHEMA_SENTRY_TRUST_PROXY_AUTH=true
SCHEMA_SENTRY_DOMAIN=schema.example.com
SCHEMA_SENTRY_DASHBOARD_BASE_URL=https://schema.example.com/
SCHEMA_SENTRY_ADMIN_USER=portfolio-owner
SCHEMA_SENTRY_ADMIN_HASH='<interactive Caddy output>'
```

Keep the bcrypt hash single-quoted because it contains `$` characters that Compose would otherwise interpolate.

The file is ignored by Git. Back it up in a password manager; do not paste it into issues, logs, screenshots, or shell history. `make prod-config` rejects missing values, known development defaults, placeholder secrets, short API/JWT secrets, non-bcrypt admin hashes, and a non-HTTPS dashboard URL.

## Validate and deploy

```bash
make prod-config
make prod-up
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml ps
```

`metadata-migrate` must exit successfully before `api` starts. Caddy waits for the API health check and obtains/renews TLS certificates automatically.

## Smoke test

Export the non-secret address and username, then run the smoke check. The password is read from the terminal without echo:

```bash
export SCHEMA_SENTRY_BASE_URL=https://schema.example.com
export SCHEMA_SENTRY_ADMIN_USER=portfolio-owner
make prod-smoke
```

For non-interactive local automation, `SCHEMA_SENTRY_SMOKE_PASSWORD` may be supplied only in the process environment and should be unset immediately afterward. The script checks authenticated liveness/readiness, the Alembic head, and Airflow health without printing response bodies or credentials.

## Routine operations

```bash
# Service status
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml ps

# Bounded JSON logs
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml logs --since=30m api airflow-scheduler

# Pull base images, rebuild the application, migrate, and restart
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml pull
make prod-up
make prod-smoke
```

Back up the Metadata Repository before upgrades. Prefer a logical backup because it is portable across hosts and can be restored into a fresh PostgreSQL volume:

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T metadata-db pg_dump -U schema_sentry -d schema_sentry --format=custom \
  > schema-sentry-metadata-$(date +%Y%m%d-%H%M%S).dump
```

Store the dump encrypted and off the mini PC. Verify it is non-empty and test restoration into a separate Compose project; never test by overwriting production. One safe rehearsal is:

```bash
docker compose -p schema-sentry-restore -f docker-compose.yml up -d --wait metadata-db
docker compose -p schema-sentry-restore -f docker-compose.yml exec -T metadata-db \
  pg_restore --clean --if-exists --no-owner -U schema_sentry -d schema_sentry \
  < schema-sentry-metadata-YYYYMMDD-HHMMSS.dump
docker compose -p schema-sentry-restore -f docker-compose.yml down --volumes
```

The production volume is project-prefixed; confirm its exact name with `docker volume ls` before any host-level snapshot. Also back up source, Airflow and Caddy state according to their recovery requirements. Do not expose database ports to the LAN.

## Secret rotation

1. Create a fresh backup and verify the current stack is healthy.
2. Generate a new application API key or Airflow JWT secret with `openssl rand -hex 32`; generate a Caddy bcrypt hash interactively.
3. Update only `.env.production`, keep mode `600`, and run `make prod-config`.
4. For the API key, update `SCHEMA_SENTRY_API_KEY` once; both API and Airflow consume the same new value when `make prod-up` recreates them.
5. For database passwords, change the PostgreSQL role password inside the private network first, then update `.env.production` and recreate dependents. Do one database at a time.
6. Run `make prod-smoke`, then revoke/delete the old credential from the password manager.

Rotation causes a short single-node restart. Do not print secret values or place them in command arguments, issue descriptions, screenshots, or Git.

## Upgrade procedure

```bash
git fetch origin
git log --oneline HEAD..origin/main
# Review release changes and take a verified metadata backup.
git pull --ff-only origin main
make prod-config
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml pull
make prod-up
make prod-smoke
```

`metadata-migrate` applies Alembic migrations before API startup. If it fails, keep the API stopped, inspect the bounded migration logs, restore the code/database pair from the verified backup if necessary, and never use `alembic stamp` to hide a mismatch.

## Failure triage

1. Run `docker compose ... ps` and identify unhealthy or exited services.
2. Inspect bounded logs with `logs --since=30m <service>`.
3. If `metadata-migrate` failed, fix the database or migration error before restarting API; never stamp a revision without verifying the schema.
4. If Caddy is unhealthy, validate DNS, ports 80/443, the bcrypt hash, and `deploy/Caddyfile`.
5. If a scan failed, use its `scan_id` and `source_key` JSON fields. Credentials are redacted by the application logger.

### Source connection or snapshot failure

- Confirm `source-db` health and network reachability from `api`.
- Verify the configured connection reference resolves to the read-only account, not an admin credential.
- Check `scan_id`, `source_key`, `error_code` and `status` in structured logs. Error text is sanitized.
- Fix connectivity or grants, then run a new scan. Never accept or create a baseline from a partial snapshot.

### Migration mismatch

- `GET /health/ready` must agree with the repository Alembic head.
- Inspect `metadata-migrate` logs and compare the database revision with `alembic heads` from the same application image.
- Do not start API/Airflow around a failed migration. Repair or restore the database, rerun migration, then smoke-test.

### Failed Slack or email delivery

- Confirm the scan itself is `COMPLETED`; provider failure is intentionally isolated from scan persistence.
- Check the delivery channel, attempt count, sanitized `last_error` and `next_retry_at` on the dashboard/API.
- Verify SMTP reachability or the Slack webhook secret without logging it.
- Retry only after `next_retry_at`. The first and second failures wait 60 and 300 seconds; a third failure is final, stores no next retry time, and no fourth attempt is allowed.

## Known operating limits

- PostgreSQL source only.
- Ten-minute polling, not real-time CDC.
- Version-controlled YAML lineage, not SQL parsing.
- One trusted operator; no in-app RBAC.
- Single mini PC; backups are required because there is no multi-node failover.
- Read-only MCP tools are not included in this project scope.
