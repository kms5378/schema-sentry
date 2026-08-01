from datetime import UTC, datetime

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from schema_sentry.domain.enums import (
    AlertChannel,
    AlertStatus,
    ChangeType,
    ScanStatus,
    ScanTrigger,
    Severity,
)
from schema_sentry.infrastructure.db.models import (
    AlertDeliveryModel,
    DatasetModel,
    DataSourceModel,
    ExpectedColumnModel,
    ScanRunModel,
    SchemaChangeModel,
)
from schema_sentry.infrastructure.db.repositories import RepositoryBundle
from schema_sentry.infrastructure.db.session import check_connection, create_session_factory


def test_repository_bundle_persists_and_queries_metadata(session: Session) -> None:
    repositories = RepositoryBundle.from_session(session)
    source = repositories.catalog.add_source(
        DataSourceModel(
            key="game",
            display_name="Game database",
            connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
        )
    )
    dataset = repositories.catalog.add_dataset(
        DatasetModel(source=source, schema_name="public", table_name="purchases")
    )
    expected = repositories.catalog.add_expected_column(
        ExpectedColumnModel(
            dataset=dataset,
            name="amount",
            data_type_json={"name": "numeric", "precision": 12, "scale": 2},
            nullable=False,
            default_expression=None,
            ordinal=4,
        )
    )
    scan = repositories.scans.add(
        ScanRunModel(
            source=source,
            trigger=ScanTrigger.MANUAL,
            status=ScanStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )
    )
    change = repositories.changes.add(
        SchemaChangeModel(
            scan=scan,
            source=source,
            dataset=dataset,
            column_name="amount",
            change_type=ChangeType.TYPE_CHANGE,
            severity=Severity.BREAKING,
            fingerprint="repository-contract",
            before_json={"name": "numeric"},
            after_json={"name": "varchar"},
            baseline_version=1,
        )
    )
    delivery = repositories.alerts.add(
        AlertDeliveryModel(
            scan=scan,
            channel=AlertChannel.SLACK,
            status=AlertStatus.PENDING,
        )
    )

    assert repositories.catalog.get_source_by_key("game") is source
    assert repositories.catalog.get_dataset(source.id, "public", "purchases") is dataset
    assert repositories.catalog.list_expected_columns(dataset.id) == (expected,)
    assert repositories.scans.get(scan.id) is scan
    assert repositories.scans.latest_for_source(source.id) is scan
    assert repositories.changes.find_open(source.id, change.fingerprint) is change
    assert repositories.changes.list_open_for_source(source.id) == (change,)
    assert repositories.alerts.list_for_scan(scan.id) == (delivery,)


def test_repository_queries_return_empty_results(session: Session) -> None:
    repositories = RepositoryBundle.from_session(session)
    source = repositories.catalog.add_source(
        DataSourceModel(key="empty", display_name="Empty", connection_ref="EMPTY_DATABASE_URL")
    )

    assert repositories.catalog.get_source_by_key("missing") is None
    assert repositories.catalog.get_dataset(source.id, "public", "missing") is None
    assert repositories.scans.latest_for_source(source.id) is None
    assert repositories.changes.list_open_for_source(source.id) == ()


def test_database_connection_helpers(migrated_engine: Engine) -> None:
    check_connection(migrated_engine)
    factory = create_session_factory(migrated_engine.url.render_as_string(hide_password=False))

    with factory() as session:
        assert session.scalar(text("SELECT 1")) == 1
