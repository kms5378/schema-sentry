from datetime import UTC, datetime
from pathlib import Path

import psycopg
from sqlalchemy import select
from sqlalchemy.orm import Session

from schema_sentry.application.catalog_service import CatalogService
from schema_sentry.application.notification_service import (
    AlertMessage,
    NotificationService,
    ProviderReceipt,
)
from schema_sentry.application.scan_service import ScanService
from schema_sentry.domain.enums import AlertChannel, AlertStatus, ScanStatus, ScanTrigger
from schema_sentry.infrastructure.db.models import (
    AlertDeliveryModel,
    DataSourceModel,
    ScanRunModel,
)
from schema_sentry.infrastructure.db.postgres_collector import PostgresSchemaCollector
from schema_sentry.infrastructure.db.repositories.alerts import AlertRepository
from schema_sentry.infrastructure.db.repositories.catalog import CatalogRepository
from schema_sentry.infrastructure.db.repositories.scans import SqlAlchemyScanRepository
from schema_sentry.infrastructure.notifications.email import EmailNotifier


class SuccessfulSlackNotifier:
    channel = AlertChannel.SLACK

    def send(self, message: AlertMessage) -> ProviderReceipt:
        return ProviderReceipt(provider_message_id="slack-demo-success")


def test_notification_channel_failure_is_isolated_and_retryable(
    system_session: Session,
    system_source_schema: None,
) -> None:
    session = system_session
    source_database_url = (
        "postgresql+psycopg://schema_sentry_reader:source_reader_dev@localhost:56432/"
        "game_source_demo"
    )
    session.add(
        DataSourceModel(
            key="game",
            display_name="Game database",
            connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
        )
    )
    session.flush()
    scans = SqlAlchemyScanRepository(
        session,
        alert_channels=(AlertChannel.EMAIL, AlertChannel.SLACK),
    )
    scan_service = ScanService(scans, lambda _: PostgresSchemaCollector(source_database_url))
    scan_service.run_scan("game", ScanTrigger.MANUAL)
    CatalogService(CatalogRepository(session)).sync(Path("catalog.yaml"))
    with psycopg.connect(
        "postgresql://game_admin:game_admin_dev@localhost:56432/game_source_demo",
        autocommit=True,
    ) as connection:
        connection.execute(Path("demo/sql/010_breaking_change.sql").read_text())
    report = scan_service.run_scan("game", ScanTrigger.MANUAL)
    failed_email = EmailNotifier(
        host="localhost",
        port=1,
        sender="schema-sentry@localhost",
        recipients=("owner@example.com",),
    )
    service = NotificationService(
        AlertRepository(session),
        (failed_email, SuccessfulSlackNotifier()),
        dashboard_base_url="http://localhost:8000/",
    )

    results = service.dispatch_scan(report.scan_id)
    deliveries = tuple(
        session.scalars(
            select(AlertDeliveryModel).order_by(AlertDeliveryModel.channel)
        )
    )
    scan = session.get(ScanRunModel, report.scan_id)

    assert scan is not None and scan.status is ScanStatus.COMPLETED
    assert {result.channel: result.success for result in results} == {
        AlertChannel.EMAIL: False,
        AlertChannel.SLACK: True,
    }
    assert {delivery.channel: delivery.status for delivery in deliveries} == {
        AlertChannel.EMAIL: AlertStatus.FAILED,
        AlertChannel.SLACK: AlertStatus.SENT,
    }

    email_delivery = next(
        delivery for delivery in deliveries if delivery.channel is AlertChannel.EMAIL
    )
    assert email_delivery.next_retry_at is not None
    retry_service = NotificationService(
        AlertRepository(session),
        (
            EmailNotifier(
                host="localhost",
                port=1125,
                sender="schema-sentry@localhost",
                recipients=("owner@example.com",),
            ),
        ),
        dashboard_base_url="http://localhost:8000/",
    )

    retried = retry_service.retry(
        email_delivery.id,
        now=max(email_delivery.next_retry_at, datetime.now(UTC)),
    )

    assert retried.success is True
    assert email_delivery.status is AlertStatus.SENT
