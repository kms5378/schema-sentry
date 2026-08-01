from collections.abc import Collection
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from schema_sentry.domain.enums import ScanTrigger
from schema_sentry.domain.models import ColumnDefinition, ColumnRef, SchemaChange


class SchemaCollector(Protocol):
    def collect(self) -> tuple[ColumnDefinition, ...]: ...


class ScanPersistence(Protocol):
    def try_source_lock(self, source_key: str) -> AbstractContextManager[bool]: ...

    def create_running_scan(self, source_key: str, trigger: ScanTrigger) -> UUID: ...

    def load_expected_columns(self, source_key: str) -> tuple[ColumnDefinition, ...]: ...

    def load_dependency_columns(self, source_key: str) -> Collection[ColumnRef]: ...

    def complete_initial_baseline(
        self,
        scan_id: UUID,
        source_key: str,
        observed: tuple[ColumnDefinition, ...],
        finished_at: datetime,
    ) -> None: ...

    def complete_drift_scan(
        self,
        scan_id: UUID,
        source_key: str,
        observed: tuple[ColumnDefinition, ...],
        changes: tuple[SchemaChange, ...],
        finished_at: datetime,
    ) -> None: ...

    def fail_scan(
        self,
        scan_id: UUID,
        error_code: str,
        error_message: str,
        finished_at: datetime,
    ) -> None: ...
