from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from schema_sentry.domain.enums import ChangeType, Severity
from schema_sentry.domain.models import DatasetRef


@dataclass(frozen=True, slots=True)
class BlockingChange:
    id: UUID
    dataset: DatasetRef
    column_name: str
    change_type: ChangeType
    severity: Severity


class ValidationPersistence(Protocol):
    def list_open_breaking_changes_for_pipeline(
        self, pipeline_key: str
    ) -> tuple[BlockingChange, ...]: ...


@dataclass(frozen=True, slots=True)
class PipelineValidation:
    pipeline_key: str
    safe: bool
    blocking_changes: tuple[BlockingChange, ...]


class ValidationService:
    def __init__(self, repository: ValidationPersistence) -> None:
        self.repository = repository

    def validate_pipeline(self, pipeline_key: str) -> PipelineValidation:
        blocking = self.repository.list_open_breaking_changes_for_pipeline(pipeline_key)
        return PipelineValidation(
            pipeline_key=pipeline_key,
            safe=not blocking,
            blocking_changes=blocking,
        )
