from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from schema_sentry.domain.enums import PipelineCriticality
from schema_sentry.domain.lineage import LineageEdge, PipelineDefinition
from schema_sentry.domain.models import ColumnRef, DatasetRef


class CatalogValidationError(ValueError):
    pass


class ColumnSetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str
    columns: tuple[str, ...] = Field(min_length=1)

    @field_validator("dataset")
    @classmethod
    def validate_dataset_name(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 2 or not all(parts):
            raise ValueError("dataset must use schema.table format")
        return value

    @field_validator("columns")
    @classmethod
    def validate_unique_columns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate column in dataset mapping")
        return value


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    airflow_dag_id: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    criticality: PipelineCriticality
    inputs: tuple[ColumnSetConfig, ...] = Field(min_length=1)
    outputs: tuple[ColumnSetConfig, ...] = Field(min_length=1)

    @field_validator("criticality", mode="before")
    @classmethod
    def normalize_criticality(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value


class CatalogConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipelines: tuple[PipelineConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pipeline_identity(self) -> "CatalogConfig":
        keys = [pipeline.key for pipeline in self.pipelines]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate pipeline key")
        dag_ids = [pipeline.airflow_dag_id for pipeline in self.pipelines]
        if len(dag_ids) != len(set(dag_ids)):
            raise ValueError("duplicate airflow DAG ID")
        return self


class CatalogPersistence(Protocol):
    def known_columns(self) -> set[ColumnRef]: ...

    def replace_catalog(
        self,
        pipelines: tuple[PipelineDefinition, ...],
        edges: tuple[LineageEdge, ...],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class CatalogSyncResult:
    pipeline_count: int
    edge_count: int


class CatalogService:
    def __init__(self, repository: CatalogPersistence) -> None:
        self.repository = repository

    def sync(self, path: Path) -> CatalogSyncResult:
        config = self._load(path)
        known_columns = self.repository.known_columns()
        pipelines: list[PipelineDefinition] = []
        edges: set[LineageEdge] = set()
        for configured in config.pipelines:
            pipeline = PipelineDefinition(
                key=configured.key,
                airflow_dag_id=configured.airflow_dag_id,
                owner=configured.owner,
                criticality=configured.criticality,
            )
            inputs = self._column_refs(configured.inputs, known_columns)
            outputs = self._column_refs(configured.outputs, known_columns)
            pipelines.append(pipeline)
            for upstream in inputs:
                for downstream in outputs:
                    if upstream == downstream:
                        raise CatalogValidationError(
                            f"self-loop lineage is not allowed: {upstream.qualified_name}"
                        )
                    edges.add(LineageEdge(pipeline, upstream, downstream))

        ordered_pipelines = tuple(sorted(pipelines, key=lambda pipeline: pipeline.key))
        ordered_edges = tuple(
            sorted(
                edges,
                key=lambda edge: (
                    edge.pipeline.key,
                    edge.upstream.qualified_name,
                    edge.downstream.qualified_name,
                ),
            )
        )
        self.repository.replace_catalog(ordered_pipelines, ordered_edges)
        return CatalogSyncResult(len(ordered_pipelines), len(ordered_edges))

    @staticmethod
    def _load(path: Path) -> CatalogConfig:
        try:
            content = yaml.safe_load(path.read_text())
            return CatalogConfig.model_validate(content)
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise CatalogValidationError(f"invalid catalog: {exc}") from exc

    @staticmethod
    def _column_refs(
        configured_sets: tuple[ColumnSetConfig, ...], known_columns: set[ColumnRef]
    ) -> tuple[ColumnRef, ...]:
        refs: list[ColumnRef] = []
        for configured in configured_sets:
            schema, table = configured.dataset.split(".")
            dataset = DatasetRef(schema, table)
            for name in configured.columns:
                ref = ColumnRef(dataset, name)
                if ref not in known_columns:
                    raise CatalogValidationError(f"unknown column: {ref.qualified_name}")
                refs.append(ref)
        return tuple(refs)
