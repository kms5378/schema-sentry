import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from schema_sentry.application.scan_service import ScanAlreadyRunning, ScanService
from schema_sentry.domain.enums import ScanStatus, ScanTrigger
from schema_sentry.infrastructure.db.models import (
    DataSourceModel,
    ExpectedColumnModel,
    ScanRunModel,
    SchemaChangeModel,
)
from schema_sentry.infrastructure.db.postgres_collector import PostgresSchemaCollector
from schema_sentry.infrastructure.db.repositories.scans import SqlAlchemyScanRepository


def test_first_and_repeated_scan_lifecycle(
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
    repository = SqlAlchemyScanRepository(session)
    service = ScanService(repository, lambda _: PostgresSchemaCollector(source_database_url))

    initial = service.run_scan("game", ScanTrigger.MANUAL)
    repeated = service.run_scan("game", ScanTrigger.SCHEDULED)

    assert initial.baseline_created is True
    assert initial.changes == ()
    assert repeated.baseline_created is False
    assert repeated.changes == ()
    assert session.scalar(select(func.count()).select_from(ExpectedColumnModel)) > 0
    assert session.scalar(select(func.count()).select_from(SchemaChangeModel)) == 0
    statuses = tuple(session.scalars(select(ScanRunModel.status).order_by(ScanRunModel.started_at)))
    assert statuses == (ScanStatus.COMPLETED, ScanStatus.COMPLETED)


def test_held_advisory_lock_rejects_concurrent_scan(
    session: Session,
    migrated_engine: Engine,
    source_database_url: str,
) -> None:
    repository = SqlAlchemyScanRepository(session)
    service = ScanService(repository, lambda _: PostgresSchemaCollector(source_database_url))
    lock = text("SELECT pg_advisory_lock(hashtextextended(:source_key, 0))")
    unlock = text("SELECT pg_advisory_unlock(hashtextextended(:source_key, 0))")

    with migrated_engine.connect() as lock_connection:
        lock_connection.execute(lock, {"source_key": "game"})
        try:
            with pytest.raises(ScanAlreadyRunning, match="game"):
                service.run_scan("game", ScanTrigger.MANUAL)
        finally:
            lock_connection.execute(unlock, {"source_key": "game"})


def test_aborted_scan_transaction_does_not_leak_advisory_lock(
    migrated_engine: Engine,
) -> None:
    try_lock = text("SELECT pg_try_advisory_lock(hashtextextended(:source_key, 0))")
    unlock = text("SELECT pg_advisory_unlock(hashtextextended(:source_key, 0))")

    with migrated_engine.connect() as first_connection:
        first_session = Session(bind=first_connection)
        repository = SqlAlchemyScanRepository(first_session)
        with pytest.raises(SQLAlchemyError), repository.try_source_lock("game") as acquired:
            assert acquired is True
            first_session.execute(text("SELECT 1 / 0"))
        first_session.rollback()

        with migrated_engine.connect() as second_connection:
            second_acquired = bool(
                second_connection.scalar(try_lock, {"source_key": "game"})
            )
            if second_acquired:
                second_connection.execute(unlock, {"source_key": "game"})

        first_connection.execute(unlock, {"source_key": "game"})

    assert second_acquired is True
