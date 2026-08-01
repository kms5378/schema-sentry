from pathlib import Path

import httpx
import psycopg
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from schema_sentry.api.app import create_app
from schema_sentry.application.catalog_service import CatalogService
from schema_sentry.application.query_service import ScanQueryService
from schema_sentry.config import Settings, get_settings
from schema_sentry.domain.enums import AlertStatus, PipelineCriticality, ScanStatus
from schema_sentry.infrastructure.db.models import (
    AlertDeliveryModel,
    DatasetModel,
    DataSourceModel,
    LineageEdgeModel,
    PipelineModel,
    ScanRunModel,
)
from schema_sentry.infrastructure.db.repositories.catalog import CatalogRepository
from schema_sentry.infrastructure.db.repositories.scans import ScanQueryRepository


def test_manual_scan_api_commits_result_and_reports_readiness(
    migrated_engine: Engine,
    source_database_url: str,
    game_source_schema: None,
) -> None:
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            DataSourceModel(
                key="game",
                display_name="Game database",
                connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
            )
        )

    settings = Settings(
        environment="test",
        metadata_database_url=migrated_engine.url.render_as_string(hide_password=False),
        source_database_url=source_database_url,
        api_key=SecretStr("integration-api-key"),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/scans",
            json={"source_key": "game"},
            headers={"X-API-Key": "integration-api-key"},
        )
        readiness = client.get("/health/ready")
        latest = client.get("/api/v1/scans/latest")

    with Session(migrated_engine) as verification_session:
        scan_count = verification_session.scalar(select(func.count()).select_from(ScanRunModel))

    assert response.status_code == 201
    assert readiness.status_code == 200
    assert latest.status_code == 200
    assert latest.json()["scan_id"] == response.json()["scan_id"]
    assert scan_count == 1


def test_source_failure_api_commits_sanitized_failed_scan(migrated_engine: Engine) -> None:
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            DataSourceModel(
                key="game",
                display_name="Game database",
                connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
            )
        )

    settings = Settings(
        environment="test",
        metadata_database_url=migrated_engine.url.render_as_string(hide_password=False),
        source_database_url="postgresql+psycopg://reader:secret@localhost:1/unavailable",
        api_key=SecretStr("integration-api-key"),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/scans",
            json={"source_key": "game"},
            headers={"X-API-Key": "integration-api-key"},
        )

    with Session(migrated_engine) as verification_session:
        scan = verification_session.scalar(select(ScanRunModel))

    assert response.status_code == 503
    assert response.json() == {"detail": "source database unavailable"}
    assert scan is not None
    assert scan.status is ScanStatus.FAILED
    assert scan.error_message == "schema collection failed"
    assert "secret" not in scan.error_message


def test_latest_scan_keeps_open_drift_visible_after_deduplicated_rescan(
    migrated_engine: Engine,
    source_database_url: str,
    game_source_schema: None,
) -> None:
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            DataSourceModel(
                key="game",
                display_name="Game database",
                connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
            )
        )
    settings = Settings(
        environment="test",
        metadata_database_url=migrated_engine.url.render_as_string(hide_password=False),
        source_database_url=source_database_url,
        api_key=SecretStr("integration-api-key"),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    headers = {"X-API-Key": "integration-api-key"}

    with TestClient(app) as client:
        assert (
            client.post("/api/v1/scans", json={"source_key": "game"}, headers=headers).status_code
            == 201
        )
        with factory.begin() as catalog_session:
            CatalogService(CatalogRepository(catalog_session)).sync(Path("catalog.yaml"))
            source = catalog_session.scalar(
                select(DataSourceModel).where(DataSourceModel.key == "game")
            )
            daily_revenue = catalog_session.scalar(
                select(DatasetModel).where(
                    DatasetModel.schema_name == "mart",
                    DatasetModel.table_name == "daily_revenue",
                )
            )
            assert source is not None
            assert daily_revenue is not None
            executive_kpi = DatasetModel(
                source=source,
                schema_name="mart",
                table_name="executive_kpi",
            )
            executive_pipeline = PipelineModel(
                key="executive_kpi",
                airflow_dag_id="executive_kpi_dag",
                owner="analytics",
                criticality=PipelineCriticality.HIGH,
            )
            catalog_session.add_all((executive_kpi, executive_pipeline))
            catalog_session.flush()
            catalog_session.add(
                LineageEdgeModel(
                    pipeline=executive_pipeline,
                    upstream_dataset=daily_revenue,
                    upstream_column="revenue",
                    downstream_dataset=executive_kpi,
                    downstream_column="total_revenue",
                )
            )
        with psycopg.connect(
            "postgresql://game_admin:game_admin_dev@localhost:55432/game_source",
            autocommit=True,
        ) as connection:
            connection.execute(Path("demo/sql/010_breaking_change.sql").read_text())
        first_drift = client.post("/api/v1/scans", json={"source_key": "game"}, headers=headers)
        repeated = client.post("/api/v1/scans", json={"source_key": "game"}, headers=headers)
        latest = client.get("/api/v1/scans/latest")

    with Session(migrated_engine) as query_session:
        recent = ScanQueryService(ScanQueryRepository(query_session)).recent(5)

    assert len(first_drift.json()["changes"]) == 1
    assert len(repeated.json()["changes"]) == 1
    assert len(latest.json()["changes"]) == 1
    assert latest.json()["changes"][0]["column_name"] == "amount"
    assert latest.json()["current_baseline_version"] == 1
    assert latest.json()["changes"][0]["affected_dags"] == [
        "daily_revenue",
        "executive_kpi_dag",
    ]
    assert [scan.id for scan in recent] == [
        scan.id for scan in sorted(recent, key=lambda scan: scan.started_at, reverse=True)
    ]
    assert len(recent) == 3


def test_api_dispatches_email_only_after_outbox_commit(
    migrated_engine: Engine,
    source_database_url: str,
    game_source_schema: None,
) -> None:
    httpx.delete("http://localhost:8025/api/v1/messages")
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            DataSourceModel(
                key="game",
                display_name="Game database",
                connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
            )
        )
    settings = Settings(
        environment="test",
        metadata_database_url=migrated_engine.url.render_as_string(hide_password=False),
        source_database_url=source_database_url,
        api_key=SecretStr("integration-api-key"),
        smtp_host="localhost",
        email_to=("owner@example.com",),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    headers = {"X-API-Key": "integration-api-key"}

    with TestClient(app) as client:
        client.post("/api/v1/scans", json={"source_key": "game"}, headers=headers)
        with psycopg.connect(
            "postgresql://game_admin:game_admin_dev@localhost:55432/game_source",
            autocommit=True,
        ) as connection:
            connection.execute(Path("demo/sql/010_breaking_change.sql").read_text())
        response = client.post("/api/v1/scans", json={"source_key": "game"}, headers=headers)
        latest = client.get("/api/v1/scans/latest")

    with Session(migrated_engine) as verification_session:
        delivery = verification_session.scalar(select(AlertDeliveryModel))
    mailpit = httpx.get("http://localhost:8025/api/v1/messages").json()

    assert response.status_code == 201
    assert delivery is not None
    assert delivery.status is AlertStatus.SENT
    assert mailpit["total"] == 1
    assert latest.json()["deliveries"][0]["channel"] == "EMAIL"
    assert latest.json()["deliveries"][0]["status"] == "SENT"
