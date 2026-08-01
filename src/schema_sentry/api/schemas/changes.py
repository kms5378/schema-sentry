from uuid import UUID

from pydantic import BaseModel, Field

from schema_sentry.application.change_service import AcceptanceResult


class AcceptChangeRequest(BaseModel):
    baseline_version: int = Field(ge=0)


class AcceptanceResponse(BaseModel):
    change_id: UUID
    baseline_version: int

    @classmethod
    def from_result(cls, result: AcceptanceResult) -> "AcceptanceResponse":
        return cls(change_id=result.change_id, baseline_version=result.baseline_version)
