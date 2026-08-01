from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from schema_sentry.application.ports import ScanPersistence, SchemaCollector
from schema_sentry.domain.diff import diff_columns
from schema_sentry.domain.enums import ScanTrigger
from schema_sentry.domain.models import SchemaChange


class ScanAlreadyRunning(RuntimeError):
    def __init__(self, source_key: str) -> None:
        super().__init__(f"scan already running for source: {source_key}")


class EmptySchemaSnapshot(RuntimeError):
    def __init__(self, source_key: str) -> None:
        super().__init__(f"schema snapshot is empty for source: {source_key}")


@dataclass(frozen=True, slots=True)
class ScanReport:
    scan_id: UUID
    source_key: str
    trigger: ScanTrigger
    baseline_created: bool
    observed_count: int
    changes: tuple[SchemaChange, ...]


class ScanService:
    def __init__(
        self,
        repository: ScanPersistence,
        collector_for: Callable[[str], SchemaCollector],
    ) -> None:
        self.repository = repository
        self.collector_for = collector_for

    def run_scan(self, source_key: str, trigger: ScanTrigger) -> ScanReport:
        with self.repository.try_source_lock(source_key) as acquired:
            if not acquired:
                raise ScanAlreadyRunning(source_key)

            scan_id = self.repository.create_running_scan(source_key, trigger)
            try:
                observed = self.collector_for(source_key).collect()
                if not observed:
                    raise EmptySchemaSnapshot(source_key)
                expected = self.repository.load_expected_columns(source_key)
                finished_at = datetime.now(UTC)
                if not expected:
                    self.repository.complete_initial_baseline(
                        scan_id, source_key, observed, finished_at
                    )
                    return ScanReport(
                        scan_id=scan_id,
                        source_key=source_key,
                        trigger=trigger,
                        baseline_created=True,
                        observed_count=len(observed),
                        changes=(),
                    )

                dependencies = self.repository.load_dependency_columns(source_key)
                changes = diff_columns(expected, observed, dependencies)
                self.repository.complete_drift_scan(
                    scan_id, source_key, observed, changes, finished_at
                )
                return ScanReport(
                    scan_id=scan_id,
                    source_key=source_key,
                    trigger=trigger,
                    baseline_created=False,
                    observed_count=len(observed),
                    changes=changes,
                )
            except Exception as exc:
                self.repository.fail_scan(
                    scan_id,
                    type(exc).__name__,
                    "schema collection failed",
                    datetime.now(UTC),
                )
                raise
