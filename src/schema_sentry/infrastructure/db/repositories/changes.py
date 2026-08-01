from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from schema_sentry.application.change_service import LockedAcceptance as LockedAcceptancePort
from schema_sentry.application.validation_service import BlockingChange
from schema_sentry.domain.enums import ChangeState, ChangeType, Severity
from schema_sentry.domain.lineage import LineageEdge, LineageGraph, PipelineDefinition
from schema_sentry.domain.models import ColumnRef, DatasetRef, SchemaChange
from schema_sentry.infrastructure.db.models import (
    DatasetModel,
    DataSourceModel,
    ExpectedColumnModel,
    LineageEdgeModel,
    PipelineModel,
    SchemaChangeModel,
)


class SqlAlchemyLockedAcceptance:
    def __init__(
        self,
        session: Session,
        source: DataSourceModel,
        change: SchemaChangeModel,
    ) -> None:
        self.session = session
        self.source = source
        self.change = change

    @property
    def baseline_version(self) -> int:
        return self.source.baseline_version

    def apply(self) -> int:
        expected = self.session.scalar(
            select(ExpectedColumnModel).where(
                ExpectedColumnModel.dataset_id == self.change.dataset_id,
                ExpectedColumnModel.name == self.change.column_name,
            )
        )
        after = self.change.after_json
        if self.change.change_type is ChangeType.ADD_COLUMN:
            if after is None:
                raise ValueError("added column change is missing after metadata")
            if expected is None:
                expected = ExpectedColumnModel(
                    dataset_id=self.change.dataset_id,
                    name=self.change.column_name,
                    data_type_json=self._data_type(after),
                    nullable=bool(after["nullable"]),
                    default_expression=self._optional_string(after.get("default")),
                    ordinal=int(after.get("ordinal", 0)),
                )
                self.session.add(expected)
        elif self.change.change_type is ChangeType.DROP_COLUMN:
            if expected is None:
                raise ValueError("dropped baseline column does not exist")
            self.session.delete(expected)
        else:
            if expected is None or after is None:
                raise ValueError("changed baseline column metadata is incomplete")
            expected.data_type_json = self._data_type(after)
            expected.nullable = bool(after["nullable"])
            expected.default_expression = self._optional_string(after.get("default"))

        self.source.baseline_version += 1
        self.change.state = ChangeState.ACCEPTED
        self.change.accepted_at = datetime.now(UTC)
        self.session.flush()
        return self.source.baseline_version

    @staticmethod
    def _data_type(payload: dict[str, Any]) -> dict[str, Any]:
        data_type = payload.get("data_type")
        if not isinstance(data_type, dict):
            raise ValueError("column metadata is missing data_type")
        return data_type

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) else None


class ChangeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, change: SchemaChangeModel) -> SchemaChangeModel:
        self.session.add(change)
        self.session.flush()
        return change

    def find_open(self, source_id: UUID, fingerprint: str) -> SchemaChangeModel | None:
        return self.session.scalar(
            select(SchemaChangeModel).where(
                SchemaChangeModel.source_id == source_id,
                SchemaChangeModel.fingerprint == fingerprint,
                SchemaChangeModel.state == ChangeState.OPEN,
            )
        )

    def list_open_for_source(self, source_id: UUID) -> tuple[SchemaChangeModel, ...]:
        statement = (
            select(SchemaChangeModel)
            .where(
                SchemaChangeModel.source_id == source_id,
                SchemaChangeModel.state == ChangeState.OPEN,
            )
            .order_by(SchemaChangeModel.created_at, SchemaChangeModel.id)
        )
        return tuple(self.session.scalars(statement))

    @contextmanager
    def acceptance_transaction(
        self, change_id: UUID
    ) -> Iterator[LockedAcceptancePort | None]:
        change = self.session.scalar(
            select(SchemaChangeModel).where(
                SchemaChangeModel.id == change_id,
                SchemaChangeModel.state == ChangeState.OPEN,
            )
        )
        if change is None:
            yield None
            return
        source = self.session.scalar(
            select(DataSourceModel).where(DataSourceModel.id == change.source_id).with_for_update()
        )
        if source is None:
            yield None
            return
        yield SqlAlchemyLockedAcceptance(self.session, source, change)

    def list_open_breaking_changes_for_pipeline(
        self, pipeline_key: str
    ) -> tuple[BlockingChange, ...]:
        pipeline_exists = self.session.scalar(
            select(PipelineModel.id).where(PipelineModel.key == pipeline_key)
        )
        if pipeline_exists is None:
            raise LookupError(f"pipeline not found: {pipeline_key}")

        upstream_dataset = aliased(DatasetModel)
        downstream_dataset = aliased(DatasetModel)
        edge_statement = (
            select(
                LineageEdgeModel,
                PipelineModel,
                upstream_dataset,
                downstream_dataset,
            )
            .join(PipelineModel, LineageEdgeModel.pipeline_id == PipelineModel.id)
            .join(upstream_dataset, LineageEdgeModel.upstream_dataset_id == upstream_dataset.id)
            .join(
                downstream_dataset,
                LineageEdgeModel.downstream_dataset_id == downstream_dataset.id,
            )
        )
        edges = tuple(
            LineageEdge(
                pipeline=PipelineDefinition(
                    key=pipeline.key,
                    airflow_dag_id=pipeline.airflow_dag_id,
                    owner=pipeline.owner,
                    criticality=pipeline.criticality,
                ),
                upstream=ColumnRef(
                    DatasetRef(upstream.schema_name, upstream.table_name),
                    edge.upstream_column,
                ),
                downstream=ColumnRef(
                    DatasetRef(downstream.schema_name, downstream.table_name),
                    edge.downstream_column,
                ),
            )
            for edge, pipeline, upstream, downstream in self.session.execute(
                edge_statement
            ).tuples()
        )
        graph = LineageGraph(edges)
        change_statement = (
            select(SchemaChangeModel, DatasetModel)
            .join(DatasetModel, SchemaChangeModel.dataset_id == DatasetModel.id)
            .where(
                SchemaChangeModel.state == ChangeState.OPEN,
                SchemaChangeModel.severity == Severity.BREAKING,
            )
        )
        blocking: list[BlockingChange] = []
        for change, dataset in self.session.execute(change_statement).tuples():
            domain_change = SchemaChange(
                dataset=DatasetRef(dataset.schema_name, dataset.table_name),
                column_name=change.column_name,
                change_type=change.change_type,
                severity=change.severity,
                before=None,
                after=None,
            )
            if any(
                impact.pipeline.key == pipeline_key for impact in graph.impacts((domain_change,))
            ):
                blocking.append(
                    BlockingChange(
                        id=change.id,
                        dataset=domain_change.dataset,
                        column_name=change.column_name,
                        change_type=change.change_type,
                        severity=change.severity,
                    )
                )
        return tuple(
            sorted(
                blocking,
                key=lambda change: (
                    change.dataset.schema,
                    change.dataset.table,
                    change.column_name,
                    str(change.id),
                ),
            )
        )
