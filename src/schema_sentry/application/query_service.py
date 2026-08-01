from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from schema_sentry.domain.enums import (
    ChangeState,
    ChangeType,
    ScanStatus,
    ScanTrigger,
    Severity,
)
from schema_sentry.domain.models import DatasetRef


@dataclass(frozen=True, slots=True)
class PersistedChange:
    id: UUID
    dataset: DatasetRef
    column_name: str
    change_type: ChangeType
    severity: Severity
    state: ChangeState
    before: dict[str, Any] | None
    after: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class PersistedScan:
    id: UUID
    source_key: str
    trigger: ScanTrigger
    status: ScanStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    changes: tuple[PersistedChange, ...]


class ScanQueryPersistence(Protocol):
    def latest(self) -> PersistedScan | None: ...

    def get(self, scan_id: UUID) -> PersistedScan | None: ...


class ScanQueryService:
    def __init__(self, repository: ScanQueryPersistence) -> None:
        self.repository = repository

    def latest(self) -> PersistedScan | None:
        return self.repository.latest()

    def get(self, scan_id: UUID) -> PersistedScan | None:
        return self.repository.get(scan_id)
