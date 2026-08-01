from pathlib import Path

import psycopg
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from schema_sentry.application.catalog_service import CatalogService
from schema_sentry.application.change_service import BaselineVersionConflict, ChangeService
from schema_sentry.application.scan_service import ScanService
from schema_sentry.application.validation_service import ValidationService
from schema_sentry.domain.enums import ChangeState, ScanTrigger
from schema_sentry.infrastructure.db.models import (
    DataSourceModel,
    ExpectedColumnModel,
    SchemaChangeModel,
)
from schema_sentry.infrastructure.db.postgres_collector import PostgresSchemaCollector
from schema_sentry.infrastructure.db.repositories.catalog import CatalogRepository
from schema_sentry.infrastructure.db.repositories.changes import ChangeRepository
from schema_sentry.infrastructure.db.repositories.scans import SqlAlchemyScanRepository


def prepare_services(
    session: Session, source_database_url: str
) -> tuple[ScanService, ChangeService, ValidationService]:
    source = DataSourceModel(
        key="game",
        display_name="Game database",
        connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
    )
    session.add(source)
    session.flush()
    scan_repository = SqlAlchemyScanRepository(session)
    scan_service = ScanService(
        scan_repository, lambda _: PostgresSchemaCollector(source_database_url)
    )
    scan_service.run_scan("game", ScanTrigger.MANUAL)
    CatalogService(CatalogRepository(session)).sync(Path("catalog.yaml"))
    changes = ChangeRepository(session)
    return scan_service, ChangeService(changes), ValidationService(changes)


def apply_ddl(sql_path: str) -> None:
    database_url = "postgresql://game_admin:game_admin_dev@localhost:55432/game_source"
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(Path(sql_path).read_text())


def test_breaking_repeat_and_restore_lifecycle(
    session: Session,
    source_database_url: str,
    game_source_schema: None,
) -> None:
    scan_service, _, validation_service = prepare_services(session, source_database_url)
    apply_ddl("demo/sql/010_breaking_change.sql")

    breaking = scan_service.run_scan("game", ScanTrigger.MANUAL)
    repeated = scan_service.run_scan("game", ScanTrigger.SCHEDULED)

    assert len(breaking.changes) == 1
    assert len(repeated.changes) == 1
    assert session.scalar(select(func.count()).select_from(SchemaChangeModel)) == 1
    assert validation_service.validate_pipeline("daily_revenue").safe is False

    apply_ddl("demo/sql/011_restore_schema.sql")
    restored = scan_service.run_scan("game", ScanTrigger.MANUAL)
    persisted = session.scalar(select(SchemaChangeModel))

    assert restored.changes == ()
    assert persisted is not None
    assert persisted.state is ChangeState.RESOLVED
    assert persisted.resolved_at is not None
    assert validation_service.validate_pipeline("daily_revenue").safe is True


def test_acceptance_uses_optimistic_baseline_version(
    session: Session,
    source_database_url: str,
    game_source_schema: None,
) -> None:
    scan_service, change_service, _ = prepare_services(session, source_database_url)
    apply_ddl("demo/sql/010_breaking_change.sql")
    scan_service.run_scan("game", ScanTrigger.MANUAL)
    change = session.scalar(select(SchemaChangeModel))
    assert change is not None

    with pytest.raises(BaselineVersionConflict):
        change_service.accept(change.id, expected_baseline_version=0)

    result = change_service.accept(change.id, expected_baseline_version=1)
    expected = session.scalar(
        select(ExpectedColumnModel).where(ExpectedColumnModel.name == "amount")
    )

    assert result.baseline_version == 2
    assert change.state is ChangeState.ACCEPTED
    assert expected is not None
    assert expected.data_type_json["name"] == "character varying"
