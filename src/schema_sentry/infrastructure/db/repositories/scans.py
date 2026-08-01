from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from schema_sentry.domain.enums import ScanStatus, ScanTrigger
from schema_sentry.domain.fingerprint import change_fingerprint
from schema_sentry.domain.models import (
    CanonicalType,
    ColumnDefinition,
    ColumnRef,
    DatasetRef,
    SchemaChange,
)
from schema_sentry.infrastructure.db.models import (
    DatasetModel,
    DataSourceModel,
    ExpectedColumnModel,
    LineageEdgeModel,
    ObservedColumnModel,
    ScanRunModel,
    SchemaChangeModel,
)


class ScanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, scan: ScanRunModel) -> ScanRunModel:
        self.session.add(scan)
        self.session.flush()
        return scan

    def get(self, scan_id: UUID) -> ScanRunModel | None:
        return self.session.get(ScanRunModel, scan_id)

    def latest_for_source(self, source_id: UUID) -> ScanRunModel | None:
        statement = (
            select(ScanRunModel)
            .where(ScanRunModel.source_id == source_id)
            .order_by(ScanRunModel.started_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)


class SourceNotFound(LookupError):
    def __init__(self, source_key: str) -> None:
        super().__init__(f"data source not found: {source_key}")


class SqlAlchemyScanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @contextmanager
    def try_source_lock(self, source_key: str) -> Iterator[bool]:
        lock_sql = text("SELECT pg_try_advisory_lock(hashtextextended(:source_key, 0))")
        unlock_sql = text("SELECT pg_advisory_unlock(hashtextextended(:source_key, 0))")
        acquired = bool(self.session.scalar(lock_sql, {"source_key": source_key}))
        try:
            yield acquired
        finally:
            if acquired:
                self.session.execute(unlock_sql, {"source_key": source_key})

    def create_running_scan(self, source_key: str, trigger: ScanTrigger) -> UUID:
        source = self._source(source_key)
        scan = ScanRunModel(
            source=source,
            trigger=trigger,
            status=ScanStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        self.session.add(scan)
        self.session.flush()
        return scan.id

    def load_expected_columns(self, source_key: str) -> tuple[ColumnDefinition, ...]:
        source = self._source(source_key)
        statement = (
            select(ExpectedColumnModel, DatasetModel)
            .join(DatasetModel, ExpectedColumnModel.dataset_id == DatasetModel.id)
            .where(DatasetModel.source_id == source.id)
            .order_by(
                DatasetModel.schema_name, DatasetModel.table_name, ExpectedColumnModel.ordinal
            )
        )
        return tuple(
            ColumnDefinition(
                dataset=DatasetRef(dataset.schema_name, dataset.table_name),
                name=column.name,
                data_type=CanonicalType(**column.data_type_json),
                nullable=column.nullable,
                default=column.default_expression,
                ordinal=column.ordinal,
            )
            for column, dataset in self.session.execute(statement).tuples()
        )

    def load_dependency_columns(self, source_key: str) -> tuple[ColumnRef, ...]:
        source = self._source(source_key)
        statement = (
            select(LineageEdgeModel, DatasetModel)
            .join(DatasetModel, LineageEdgeModel.upstream_dataset_id == DatasetModel.id)
            .where(DatasetModel.source_id == source.id)
            .order_by(
                DatasetModel.schema_name, DatasetModel.table_name, LineageEdgeModel.upstream_column
            )
        )
        return tuple(
            ColumnRef(
                DatasetRef(dataset.schema_name, dataset.table_name),
                edge.upstream_column,
            )
            for edge, dataset in self.session.execute(statement).tuples()
        )

    def complete_initial_baseline(
        self,
        scan_id: UUID,
        source_key: str,
        observed: tuple[ColumnDefinition, ...],
        finished_at: datetime,
    ) -> None:
        source = self._source(source_key)
        scan = self._scan(scan_id)
        datasets = self._datasets_by_ref(source.id)
        for column in observed:
            dataset = datasets.get(column.dataset)
            if dataset is None:
                dataset = DatasetModel(
                    source=source,
                    schema_name=column.dataset.schema,
                    table_name=column.dataset.table,
                )
                self.session.add(dataset)
                self.session.flush()
                datasets[column.dataset] = dataset
            self.session.add(
                ExpectedColumnModel(
                    dataset=dataset,
                    name=column.name,
                    data_type_json=column.data_type.to_canonical_dict(),
                    nullable=column.nullable,
                    default_expression=column.default,
                    ordinal=column.ordinal,
                )
            )
        self._persist_observations(scan, observed)
        self._complete_scan(scan, finished_at)
        self.session.flush()

    def complete_drift_scan(
        self,
        scan_id: UUID,
        source_key: str,
        observed: tuple[ColumnDefinition, ...],
        changes: tuple[SchemaChange, ...],
        finished_at: datetime,
    ) -> None:
        source = self._source(source_key)
        scan = self._scan(scan_id)
        datasets = self._datasets_by_ref(source.id)
        self._persist_observations(scan, observed)
        for change in changes:
            dataset = datasets.get(change.dataset)
            if dataset is None:
                raise LookupError(f"baseline dataset not found: {change.dataset.qualified_name}")
            self.session.add(
                SchemaChangeModel(
                    scan=scan,
                    source=source,
                    dataset=dataset,
                    column_name=change.column_name,
                    change_type=change.change_type,
                    severity=change.severity,
                    fingerprint=change_fingerprint(source_key, change),
                    before_json=change.before.to_canonical_dict() if change.before else None,
                    after_json=change.after.to_canonical_dict() if change.after else None,
                    baseline_version=source.baseline_version,
                )
            )
        self._complete_scan(scan, finished_at)
        self.session.flush()

    def fail_scan(
        self,
        scan_id: UUID,
        error_code: str,
        error_message: str,
        finished_at: datetime,
    ) -> None:
        scan = self._scan(scan_id)
        scan.status = ScanStatus.FAILED
        scan.finished_at = finished_at
        scan.duration_ms = self._duration_ms(scan.started_at, finished_at)
        scan.error_code = error_code
        scan.error_message = error_message
        self.session.flush()

    def expected_column_count(self, source_key: str) -> int:
        return len(self.load_expected_columns(source_key))

    def _source(self, source_key: str) -> DataSourceModel:
        source = self.session.scalar(
            select(DataSourceModel).where(DataSourceModel.key == source_key)
        )
        if source is None:
            raise SourceNotFound(source_key)
        return source

    def _scan(self, scan_id: UUID) -> ScanRunModel:
        scan = self.session.get(ScanRunModel, scan_id)
        if scan is None:
            raise LookupError(f"scan not found: {scan_id}")
        return scan

    def _datasets_by_ref(self, source_id: UUID) -> dict[DatasetRef, DatasetModel]:
        datasets = self.session.scalars(
            select(DatasetModel).where(DatasetModel.source_id == source_id)
        )
        return {
            DatasetRef(dataset.schema_name, dataset.table_name): dataset for dataset in datasets
        }

    def _persist_observations(
        self, scan: ScanRunModel, observed: tuple[ColumnDefinition, ...]
    ) -> None:
        self.session.add_all(
            [
                ObservedColumnModel(
                    scan=scan,
                    schema_name=column.dataset.schema,
                    table_name=column.dataset.table,
                    name=column.name,
                    data_type_json=column.data_type.to_canonical_dict(),
                    nullable=column.nullable,
                    default_expression=column.default,
                    ordinal=column.ordinal,
                )
                for column in observed
            ]
        )

    def _complete_scan(self, scan: ScanRunModel, finished_at: datetime) -> None:
        scan.status = ScanStatus.COMPLETED
        scan.finished_at = finished_at
        scan.duration_ms = self._duration_ms(scan.started_at, finished_at)

    @staticmethod
    def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
        return max(0, int((finished_at - started_at).total_seconds() * 1000))
