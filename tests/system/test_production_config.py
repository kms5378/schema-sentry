import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
KNOWN_UNSAFE_VALUES = {
    "game_admin_dev",
    "source_reader_dev",
    "pipeline_writer_dev",
    "schema_sentry_dev",
    "airflow_dev",
    "replace-with-openssl-rand-hex-32",
}


def render_production_compose() -> dict[str, Any]:
    environment = {
        **os.environ,
        "SCHEMA_SENTRY_DOMAIN": "schema.example.test",
        "SCHEMA_SENTRY_ADMIN_USER": "portfolio-owner",
        "SCHEMA_SENTRY_ADMIN_HASH": "$2a$14$test-only-hash",
        "SCHEMA_SENTRY_API_KEY": "test-only-api-key",
        "SCHEMA_SENTRY_DASHBOARD_BASE_URL": "https://schema.example.test/",
        "SOURCE_DB_ADMIN_PASSWORD": "test-only-source-admin",
        "SOURCE_DB_READER_PASSWORD": "test-only-source-reader",
        "SOURCE_DB_PIPELINE_PASSWORD": "test-only-pipeline-writer",
        "METADATA_DB_PASSWORD": "test-only-metadata",
        "AIRFLOW_DB_PASSWORD": "test-only-airflow-db",
        "AIRFLOW_JWT_SECRET": "test-only-airflow-jwt",
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.prod.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_production_exposes_only_caddy_and_runs_migrations_first() -> None:
    config = render_production_compose()
    services = config["services"]
    published_services = {
        name for name, service in services.items() if service.get("ports")
    }

    assert published_services == {"caddy"}
    assert {port["published"] for port in services["caddy"]["ports"]} == {"80", "443"}
    assert services["caddy"]["image"] == "caddy:2.11.4-alpine"
    assert services["api"]["environment"]["SCHEMA_SENTRY_ENVIRONMENT"] == "production"
    assert services["api"]["environment"]["SCHEMA_SENTRY_AUTH_DISABLED"] == "false"
    assert services["api"]["environment"]["SCHEMA_SENTRY_TRUST_PROXY_AUTH"] == "true"
    assert services["api"]["depends_on"]["metadata-migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["metadata-migrate"]["environment"][
        "SCHEMA_SENTRY_ALEMBIC_DATABASE_URL"
    ].startswith("postgresql+psycopg://schema_sentry:")


def test_production_services_apply_container_hardening() -> None:
    services = render_production_compose()["services"]

    for service_name in ("api", "caddy", "source-permissions-init"):
        service = services[service_name]
        assert service["read_only"] is True
        assert "no-new-privileges:true" in service["security_opt"]

    for service_name, service in services.items():
        assert service["logging"]["driver"] == "json-file", service_name
        assert service["logging"]["options"] == {"max-file": "3", "max-size": "10m"}


def test_production_services_do_not_render_known_development_credentials() -> None:
    rendered = json.dumps(render_production_compose())

    assert not any(unsafe in rendered for unsafe in KNOWN_UNSAFE_VALUES)


def test_production_env_guard_rejects_development_defaults(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.production"
    env_file.write_text(
        "\n".join(
            (
                "SCHEMA_SENTRY_DOMAIN=schema.example.test",
                "SCHEMA_SENTRY_DASHBOARD_BASE_URL=https://schema.example.test/",
                "SCHEMA_SENTRY_ADMIN_USER=owner",
                "SCHEMA_SENTRY_ADMIN_HASH='$2a$14$valid-looking-test-hash'",
                "SCHEMA_SENTRY_API_KEY=replace-with-openssl-rand-hex-32",
                "SOURCE_DB_ADMIN_PASSWORD=game_admin_dev",
                "SOURCE_DB_READER_PASSWORD=source-reader",
                "SOURCE_DB_PIPELINE_PASSWORD=pipeline-writer",
                "METADATA_DB_PASSWORD=metadata-password",
                "AIRFLOW_DB_PASSWORD=airflow-password",
                "AIRFLOW_JWT_SECRET=airflow-jwt-secret",
            )
        )
    )

    result = subprocess.run(
        ["bash", "scripts/validate-production-env.sh", str(env_file)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "SCHEMA_SENTRY_API_KEY" in result.stderr
    assert "SOURCE_DB_ADMIN_PASSWORD" in result.stderr


def test_production_env_guard_accepts_non_default_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.production"
    env_file.write_text(
        "\n".join(
            (
                "SCHEMA_SENTRY_DOMAIN=schema.example.test",
                "SCHEMA_SENTRY_DASHBOARD_BASE_URL=https://schema.example.test/",
                "SCHEMA_SENTRY_ADMIN_USER=owner",
                "SCHEMA_SENTRY_ADMIN_HASH='$2a$14$valid-looking-test-hash'",
                "SCHEMA_SENTRY_API_KEY=0123456789abcdef0123456789abcdef",
                "SOURCE_DB_ADMIN_PASSWORD=source-admin-password",
                "SOURCE_DB_READER_PASSWORD=source-reader-password",
                "SOURCE_DB_PIPELINE_PASSWORD=pipeline-writer-password",
                "METADATA_DB_PASSWORD=metadata-password",
                "AIRFLOW_DB_PASSWORD=airflow-password",
                "AIRFLOW_JWT_SECRET=abcdef0123456789abcdef0123456789",
            )
        )
    )

    result = subprocess.run(
        ["bash", "scripts/validate-production-env.sh", str(env_file)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
