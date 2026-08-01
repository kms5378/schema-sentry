from uuid import UUID

from pydantic import BaseModel

from schema_sentry.application.validation_service import PipelineValidation
from schema_sentry.domain.enums import ChangeType, Severity


class BlockingChangeResponse(BaseModel):
    id: UUID
    dataset: str
    column_name: str
    change_type: ChangeType
    severity: Severity


class PipelineValidationResponse(BaseModel):
    pipeline_key: str
    safe: bool
    blocking_changes: list[BlockingChangeResponse]

    @classmethod
    def from_domain(cls, result: PipelineValidation) -> "PipelineValidationResponse":
        return cls(
            pipeline_key=result.pipeline_key,
            safe=result.safe,
            blocking_changes=[
                BlockingChangeResponse(
                    id=change.id,
                    dataset=change.dataset.qualified_name,
                    column_name=change.column_name,
                    change_type=change.change_type,
                    severity=change.severity,
                )
                for change in result.blocking_changes
            ],
        )
