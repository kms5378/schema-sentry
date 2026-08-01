from pathlib import Path

import httpx
import psycopg
from sqlalchemy import select
from sqlalchemy.orm import Session

from schema_sentry.application.catalog_service import CatalogService
from schema_sentry.application.notification_service import NotificationService
from schema_sentry.application.scan_service import ScanService
from schema_sentry.domain.enums import AlertChannel, AlertStatus, ScanTrigger
from schema_sentry.infrastructure.db.models import AlertDeliveryModel, DataSourceModel
from schema_sentry.infrastructure.db.postgres_collector import PostgresSchemaCollector
from schema_sentry.infrastructure.db.repositories.alerts import AlertRepository
from schema_sentry.infrastructure.db.repositories.catalog import CatalogRepository
from schema_sentry.infrastructure.db.repositories.scans import SqlAlchemyScanRepository
from schema_sentry.infrastructure.notifications.email import EmailNotifier


def test_pending_email_delivery_reaches_mailpit(
    session: Session,
    source_database_url: str,
    game_source_schema: None,
) -> None:
    httpx.delete("http://localhost:8025/api/v1/messages")
    session.add(
        DataSourceModel(
            key="game",
            display_name="Game database",
            connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
        )
    )
    session.flush()
    repository = SqlAlchemyScanRepository(
        session, alert_channels=(AlertChannel.EMAIL,)
    )
    scan_service = ScanService(
        repository, lambda _: PostgresSchemaCollector(source_database_url)
    )
    scan_service.run_scan("game", ScanTrigger.MANUAL)
    CatalogService(CatalogRepository(session)).sync(Path("catalog.yaml"))
    with psycopg.connect(
        "postgresql://game_admin:game_admin_dev@localhost:55432/game_source",
        autocommit=True,
    ) as connection:
        connection.execute(Path("demo/sql/010_breaking_change.sql").read_text())
    report = scan_service.run_scan("game", ScanTrigger.MANUAL)

    results = NotificationService(
        AlertRepository(session),
        (
            EmailNotifier(
                host="localhost",
                port=1025,
                sender="schema-sentry@localhost",
                recipients=("owner@example.com",),
            ),
        ),
        dashboard_base_url="http://localhost:8000/",
    ).dispatch_scan(report.scan_id)

    delivery = session.scalar(select(AlertDeliveryModel))
    messages = httpx.get("http://localhost:8025/api/v1/messages").json()
    assert results[0].success is True
    assert delivery is not None
    assert delivery.status is AlertStatus.SENT
    assert messages["total"] == 1
    assert "Schema Sentry drift detected" in messages["messages"][0]["Subject"]
