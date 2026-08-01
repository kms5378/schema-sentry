from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

import structlog

from schema_sentry.application.ports import ScanPersistence, SchemaCollector
from schema_sentry.domain.diff import diff_columns
from schema_sentry.domain.enums import ScanTrigger
from schema_sentry.domain.models import SchemaChange
from schema_sentry.logging import log_source_failure

logger = structlog.get_logger(__name__)


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

            started = perf_counter()
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
                    report = ScanReport(
                        scan_id=scan_id,
                        source_key=source_key,
                        trigger=trigger,
                        baseline_created=True,
                        observed_count=len(observed),
                        changes=(),
                    )
                    self._log_completed(report, started)
                    return report

                dependencies = self.repository.load_dependency_columns(source_key)
                changes = diff_columns(expected, observed, dependencies)
                self.repository.complete_drift_scan(
                    scan_id, source_key, observed, changes, finished_at
                )
                report = ScanReport(
                    scan_id=scan_id,
                    source_key=source_key,
                    trigger=trigger,
                    baseline_created=False,
                    observed_count=len(observed),
                    changes=changes,
                )
                self._log_completed(report, started)
                return report
            except Exception as exc:
                self.repository.fail_scan(
                    scan_id,
                    type(exc).__name__,
                    "schema collection failed",
                    datetime.now(UTC),
                )
                log_source_failure(
                    exc,
                    source_key=source_key,
                    scan_id=str(scan_id),
                    duration_ms=self._duration_ms(started),
                )
                raise

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))

    @classmethod
    def _log_completed(cls, report: ScanReport, started: float) -> None:
        with suppress(OSError, ValueError):
            logger.info(
                "schema_scan_completed",
                scan_id=str(report.scan_id),
                source_key=report.source_key,
                duration_ms=cls._duration_ms(started),
                status="COMPLETED",
                trigger=report.trigger.value,
                observed_count=report.observed_count,
                change_count=len(report.changes),
            )
