from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from schema_sentry.domain.enums import (
    AlertChannel,
    AlertStatus,
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
    affected_dags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersistedDelivery:
    id: UUID
    channel: AlertChannel
    status: AlertStatus
    attempt_count: int
    provider_message_id: str | None
    last_error: str | None
    next_retry_at: datetime | None
    sent_at: datetime | None


@dataclass(frozen=True, slots=True)
class PersistedScan:
    id: UUID
    source_key: str
    current_baseline_version: int
    trigger: ScanTrigger
    status: ScanStatus
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    changes: tuple[PersistedChange, ...]
    deliveries: tuple[PersistedDelivery, ...] = ()


class ScanQueryPersistence(Protocol):
    def latest(self) -> PersistedScan | None: ...

    def get(self, scan_id: UUID) -> PersistedScan | None: ...

    def recent(self, limit: int) -> tuple[PersistedScan, ...]: ...


class ScanQueryService:
    def __init__(self, repository: ScanQueryPersistence) -> None:
        self.repository = repository

    def latest(self) -> PersistedScan | None:
        return self.repository.latest()

    def get(self, scan_id: UUID) -> PersistedScan | None:
        return self.repository.get(scan_id)

    def recent(self, limit: int = 5) -> tuple[PersistedScan, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("recent scan limit must be between 1 and 50")
        return self.repository.recent(limit)
