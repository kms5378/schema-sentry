from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from schema_sentry.domain.enums import ChangeState, ChangeType, ScanStatus, ScanTrigger, Severity
from schema_sentry.infrastructure.db.models import (
    DatasetModel,
    DataSourceModel,
    ScanRunModel,
    SchemaChangeModel,
)
from schema_sentry.infrastructure.db.session import session_scope


def make_source(*, key: str = "game") -> DataSourceModel:
    return DataSourceModel(
        key=key,
        display_name="Game database",
        connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
    )


def make_change(
    *,
    source: DataSourceModel,
    dataset: DatasetModel,
    scan: ScanRunModel,
    state: ChangeState = ChangeState.OPEN,
) -> SchemaChangeModel:
    return SchemaChangeModel(
        scan=scan,
        source=source,
        dataset=dataset,
        column_name="amount",
        change_type=ChangeType.TYPE_CHANGE,
        severity=Severity.BREAKING,
        state=state,
        fingerprint="stable-fingerprint",
        before_json={"data_type": "numeric(12,2)"},
        after_json={"data_type": "varchar"},
        baseline_version=1,
    )


def persist_change_dependencies(
    session: Session,
) -> tuple[DataSourceModel, DatasetModel, ScanRunModel]:
    source = make_source()
    dataset = DatasetModel(source=source, schema_name="public", table_name="purchases")
    scan = ScanRunModel(
        source=source,
        trigger=ScanTrigger.MANUAL,
        status=ScanStatus.COMPLETED,
        started_at=datetime.now(UTC),
    )
    session.add_all([source, dataset, scan])
    session.flush()
    return source, dataset, scan


def test_data_source_key_is_unique(session: Session) -> None:
    session.add_all([make_source(), make_source()])

    with pytest.raises(IntegrityError):
        session.commit()


def test_dataset_identity_is_unique_within_source(session: Session) -> None:
    source = make_source()
    session.add_all(
        [
            DatasetModel(source=source, schema_name="public", table_name="purchases"),
            DatasetModel(source=source, schema_name="public", table_name="purchases"),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_only_one_open_fingerprint_per_source(session: Session) -> None:
    source, dataset, scan = persist_change_dependencies(session)
    session.add_all(
        [
            make_change(source=source, dataset=dataset, scan=scan),
            make_change(source=source, dataset=dataset, scan=scan),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_resolved_fingerprint_may_reoccur_as_open(session: Session) -> None:
    source, dataset, scan = persist_change_dependencies(session)
    session.add_all(
        [
            make_change(
                source=source,
                dataset=dataset,
                scan=scan,
                state=ChangeState.RESOLVED,
            ),
            make_change(source=source, dataset=dataset, scan=scan),
        ]
    )

    session.commit()


def test_session_scope_commits_and_rolls_back(migrated_engine: Engine) -> None:
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with session_scope(factory) as scoped_session:
        scoped_session.add(make_source(key="committed"))

    with factory() as verification_session:
        assert verification_session.query(DataSourceModel).filter_by(key="committed").one()

    with (
        pytest.raises(RuntimeError, match="force rollback"),
        session_scope(factory) as scoped_session,
    ):
        scoped_session.add(make_source(key="rolled-back"))
        raise RuntimeError("force rollback")

    with factory() as verification_session:
        assert (
            verification_session.query(DataSourceModel).filter_by(key="rolled-back").first() is None
        )


def test_models_generate_uuid_primary_keys(session: Session) -> None:
    source = make_source(key=f"source-{uuid4()}")
    session.add(source)
    session.flush()

    assert source.id is not None
