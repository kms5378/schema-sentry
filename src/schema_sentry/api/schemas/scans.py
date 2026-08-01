from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from schema_sentry.application.query_service import PersistedChange, PersistedScan
from schema_sentry.application.scan_service import ScanReport
from schema_sentry.domain.enums import ChangeState, ChangeType, ScanStatus, ScanTrigger, Severity


class ManualScanRequest(BaseModel):
    source_key: str = Field(min_length=1, max_length=100)


class ScanChangeResponse(BaseModel):
    id: UUID | None = None
    dataset: str
    column_name: str
    change_type: ChangeType
    severity: Severity
    state: ChangeState | None = None
    before: dict[str, Any] | None
    after: dict[str, Any] | None

    @classmethod
    def from_persisted(cls, change: PersistedChange) -> "ScanChangeResponse":
        return cls(
            id=change.id,
            dataset=change.dataset.qualified_name,
            column_name=change.column_name,
            change_type=change.change_type,
            severity=change.severity,
            state=change.state,
            before=change.before,
            after=change.after,
        )


class ScanResponse(BaseModel):
    scan_id: UUID
    source_key: str
    trigger: ScanTrigger
    baseline_created: bool
    observed_count: int
    changes: list[ScanChangeResponse]

    @classmethod
    def from_report(cls, report: ScanReport) -> "ScanResponse":
        return cls(
            scan_id=report.scan_id,
            source_key=report.source_key,
            trigger=report.trigger,
            baseline_created=report.baseline_created,
            observed_count=report.observed_count,
            changes=[
                ScanChangeResponse(
                    dataset=change.dataset.qualified_name,
                    column_name=change.column_name,
                    change_type=change.change_type,
                    severity=change.severity,
                    before=change.before.to_canonical_dict() if change.before else None,
                    after=change.after.to_canonical_dict() if change.after else None,
                )
                for change in report.changes
            ],
        )


class ScanDetailResponse(BaseModel):
    scan_id: UUID
    source_key: str
    trigger: ScanTrigger
    status: ScanStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    changes: list[ScanChangeResponse]

    @classmethod
    def from_persisted(cls, scan: PersistedScan) -> "ScanDetailResponse":
        return cls(
            scan_id=scan.id,
            source_key=scan.source_key,
            trigger=scan.trigger,
            status=scan.status,
            started_at=scan.started_at,
            finished_at=scan.finished_at,
            duration_ms=scan.duration_ms,
            error_code=scan.error_code,
            error_message=scan.error_message,
            changes=[ScanChangeResponse.from_persisted(change) for change in scan.changes],
        )
