from pathlib import Path

import psycopg
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from schema_sentry.application.scan_service import ScanService
from schema_sentry.domain.enums import AlertChannel, AlertStatus, ScanTrigger
from schema_sentry.infrastructure.db.models import AlertDeliveryModel, DataSourceModel
from schema_sentry.infrastructure.db.postgres_collector import PostgresSchemaCollector
from schema_sentry.infrastructure.db.repositories.scans import SqlAlchemyScanRepository


def test_new_drift_creates_one_pending_delivery_per_enabled_channel(
    session: Session,
    source_database_url: str,
    game_source_schema: None,
) -> None:
    session.add(
        DataSourceModel(
            key="game",
            display_name="Game database",
            connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
        )
    )
    session.flush()
    repository = SqlAlchemyScanRepository(
        session, alert_channels=(AlertChannel.SLACK, AlertChannel.EMAIL)
    )
    service = ScanService(repository, lambda _: PostgresSchemaCollector(source_database_url))
    service.run_scan("game", ScanTrigger.MANUAL)
    with psycopg.connect(
        "postgresql://game_admin:game_admin_dev@localhost:55432/game_source",
        autocommit=True,
    ) as connection:
        connection.execute(Path("demo/sql/010_breaking_change.sql").read_text())

    service.run_scan("game", ScanTrigger.MANUAL)
    service.run_scan("game", ScanTrigger.SCHEDULED)

    assert session.scalar(select(func.count()).select_from(AlertDeliveryModel)) == 2
    deliveries = tuple(session.scalars(select(AlertDeliveryModel)))
    assert {delivery.channel for delivery in deliveries} == {
        AlertChannel.SLACK,
        AlertChannel.EMAIL,
    }
    assert {delivery.status for delivery in deliveries} == {AlertStatus.PENDING}


def test_failed_scan_creates_sanitized_system_alert_outbox(session: Session) -> None:
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
    service = ScanService(
        repository,
        lambda _: PostgresSchemaCollector(
            "postgresql+psycopg://reader:secret@localhost:1/unavailable"
        ),
    )

    with pytest.raises(psycopg.Error):
        service.run_scan("game", ScanTrigger.MANUAL)

    delivery = session.scalar(select(AlertDeliveryModel))
    assert delivery is not None
    assert delivery.status is AlertStatus.PENDING
