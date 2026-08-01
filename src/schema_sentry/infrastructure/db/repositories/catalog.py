import hashlib
import json
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from schema_sentry.domain.lineage import LineageEdge, PipelineDefinition
from schema_sentry.domain.models import ColumnRef, DatasetRef
from schema_sentry.infrastructure.db.models import (
    DatasetModel,
    DataSourceModel,
    ExpectedColumnModel,
    LineageEdgeModel,
    PipelineModel,
)


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_source(self, source: DataSourceModel) -> DataSourceModel:
        self.session.add(source)
        self.session.flush()
        return source

    def get_source_by_key(self, key: str) -> DataSourceModel | None:
        return self.session.scalar(select(DataSourceModel).where(DataSourceModel.key == key))

    def add_dataset(self, dataset: DatasetModel) -> DatasetModel:
        self.session.add(dataset)
        self.session.flush()
        return dataset

    def get_dataset(self, source_id: UUID, schema: str, table: str) -> DatasetModel | None:
        return self.session.scalar(
            select(DatasetModel).where(
                DatasetModel.source_id == source_id,
                DatasetModel.schema_name == schema,
                DatasetModel.table_name == table,
            )
        )

    def add_expected_column(self, column: ExpectedColumnModel) -> ExpectedColumnModel:
        self.session.add(column)
        self.session.flush()
        return column

    def list_expected_columns(self, dataset_id: UUID) -> tuple[ExpectedColumnModel, ...]:
        statement = (
            select(ExpectedColumnModel)
            .where(ExpectedColumnModel.dataset_id == dataset_id)
            .order_by(ExpectedColumnModel.ordinal)
        )
        return tuple(self.session.scalars(statement))

    def known_columns(self) -> set[ColumnRef]:
        statement = select(ExpectedColumnModel, DatasetModel).join(
            DatasetModel, ExpectedColumnModel.dataset_id == DatasetModel.id
        )
        return {
            ColumnRef(DatasetRef(dataset.schema_name, dataset.table_name), column.name)
            for column, dataset in self.session.execute(statement).tuples()
        }

    def replace_catalog(
        self,
        pipelines: tuple[PipelineDefinition, ...],
        edges: tuple[LineageEdge, ...],
    ) -> None:
        datasets = tuple(self.session.scalars(select(DatasetModel)))
        datasets_by_ref = {
            DatasetRef(dataset.schema_name, dataset.table_name): dataset for dataset in datasets
        }
        self.session.execute(delete(LineageEdgeModel))
        self.session.execute(delete(PipelineModel))
        self.session.flush()

        pipeline_models: dict[str, PipelineModel] = {}
        for pipeline in pipelines:
            model = PipelineModel(
                key=pipeline.key,
                airflow_dag_id=pipeline.airflow_dag_id,
                owner=pipeline.owner,
                criticality=pipeline.criticality,
            )
            self.session.add(model)
            pipeline_models[pipeline.key] = model
        self.session.flush()

        for edge in edges:
            self.session.add(
                LineageEdgeModel(
                    pipeline=pipeline_models[edge.pipeline.key],
                    upstream_dataset=datasets_by_ref[edge.upstream.dataset],
                    upstream_column=edge.upstream.name,
                    downstream_dataset=datasets_by_ref[edge.downstream.dataset],
                    downstream_column=edge.downstream.name,
                )
            )
        self.session.flush()

    def catalog_digest(self) -> str:
        pipelines = tuple(self.session.scalars(select(PipelineModel).order_by(PipelineModel.key)))
        edge_rows = self.session.execute(
            select(LineageEdgeModel, PipelineModel)
            .join(PipelineModel, LineageEdgeModel.pipeline_id == PipelineModel.id)
            .order_by(
                PipelineModel.key,
                LineageEdgeModel.upstream_dataset_id,
                LineageEdgeModel.upstream_column,
                LineageEdgeModel.downstream_dataset_id,
                LineageEdgeModel.downstream_column,
            )
        ).tuples()
        payload = {
            "pipelines": [
                {
                    "key": pipeline.key,
                    "airflow_dag_id": pipeline.airflow_dag_id,
                    "owner": pipeline.owner,
                    "criticality": pipeline.criticality.value,
                }
                for pipeline in pipelines
            ],
            "edges": [
                {
                    "pipeline": pipeline.key,
                    "upstream_dataset_id": str(edge.upstream_dataset_id),
                    "upstream_column": edge.upstream_column,
                    "downstream_dataset_id": str(edge.downstream_dataset_id),
                    "downstream_column": edge.downstream_column,
                }
                for edge, pipeline in edge_rows
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()
