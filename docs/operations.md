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

Back up the named `metadata-data`, `source-data`, `airflow-data`, and `caddy-data` volumes before host upgrades. Test restoration on a separate machine. Do not expose database ports to the LAN.

## Failure triage

1. Run `docker compose ... ps` and identify unhealthy or exited services.
2. Inspect bounded logs with `logs --since=30m <service>`.
3. If `metadata-migrate` failed, fix the database or migration error before restarting API; never stamp a revision without verifying the schema.
4. If Caddy is unhealthy, validate DNS, ports 80/443, the bcrypt hash, and `deploy/Caddyfile`.
5. If a scan failed, use its `scan_id` and `source_key` JSON fields. Credentials are redacted by the application logger.
