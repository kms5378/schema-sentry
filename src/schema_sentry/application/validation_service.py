from contextlib import suppress
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol
from uuid import UUID

import structlog

from schema_sentry.domain.enums import ChangeType, Severity
from schema_sentry.domain.models import DatasetRef

logger = structlog.get_logger(__name__)


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
        started = perf_counter()
        blocking = self.repository.list_open_breaking_changes_for_pipeline(pipeline_key)
        result = PipelineValidation(
            pipeline_key=pipeline_key,
            safe=not blocking,
            blocking_changes=blocking,
        )
        with suppress(OSError, ValueError):
            logger.info(
                "pipeline_validation_completed",
                pipeline_key=pipeline_key,
                duration_ms=max(0, round((perf_counter() - started) * 1000)),
                status="SAFE" if result.safe else "BLOCKED",
                blocking_change_count=len(blocking),
            )
        return result
