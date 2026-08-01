import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from schema_sentry.application.ports import SchemaCollector
from schema_sentry.application.scan_service import (
    EmptySchemaSnapshot,
    ScanAlreadyRunning,
    ScanService,
)
from schema_sentry.domain.enums import ScanStatus, ScanTrigger
from schema_sentry.domain.models import CanonicalType, ColumnDefinition, DatasetRef


def sample_columns() -> tuple[ColumnDefinition, ...]:
    return (
        ColumnDefinition(
            dataset=DatasetRef("public", "purchases"),
            name="amount",
            data_type=CanonicalType("numeric", precision=12, scale=2),
            nullable=False,
            default=None,
        ),
    )


class StubCollector:
    def __init__(self, columns: tuple[ColumnDefinition, ...]) -> None:
        self.columns = columns

    def collect(self) -> tuple[ColumnDefinition, ...]:
        return self.columns


class FailingCollector:
    def collect(self) -> tuple[ColumnDefinition, ...]:
        raise ConnectionError("password=must-not-be-persisted")


class FakeScanRepository:
    def __init__(self, *, lock_acquired: bool = True) -> None:
        self.lock_acquired = lock_acquired
        self.expected: tuple[ColumnDefinition, ...] = ()
        self.scan_id = uuid4()
        self.status: ScanStatus | None = None
        self.error: tuple[str, str] | None = None

    @contextmanager
    def try_source_lock(self, source_key: str) -> Iterator[bool]:
        yield self.lock_acquired

    def create_running_scan(self, source_key: str, trigger: ScanTrigger) -> UUID:
        self.status = ScanStatus.RUNNING
        return self.scan_id

    def load_expected_columns(self, source_key: str) -> tuple[ColumnDefinition, ...]:
        return self.expected

    def load_dependency_columns(self, source_key: str) -> tuple[object, ...]:
        return ()

    def complete_initial_baseline(
        self,
        scan_id: UUID,
        source_key: str,
        observed: tuple[ColumnDefinition, ...],
        finished_at: datetime,
    ) -> None:
        self.expected = observed
        self.status = ScanStatus.COMPLETED

    def complete_drift_scan(
        self,
        scan_id: UUID,
        source_key: str,
        observed: tuple[ColumnDefinition, ...],
        changes: tuple[object, ...],
        finished_at: datetime,
    ) -> None:
        self.status = ScanStatus.COMPLETED

    def fail_scan(
        self,
        scan_id: UUID,
        error_code: str,
        error_message: str,
        finished_at: datetime,
    ) -> None:
        self.status = ScanStatus.FAILED
        self.error = (error_code, error_message)


def collector_factory(collector: SchemaCollector):
    return lambda source_key: collector


def test_first_scan_creates_baseline_without_changes() -> None:
    repository = FakeScanRepository()
    service = ScanService(repository, collector_factory(StubCollector(sample_columns())))

    report = service.run_scan("game", ScanTrigger.MANUAL)

    assert report.baseline_created is True
    assert report.changes == ()
    assert report.observed_count == 1
    assert repository.expected == sample_columns()
    assert repository.status is ScanStatus.COMPLETED


def test_repeated_unchanged_scan_has_no_changes() -> None:
    repository = FakeScanRepository()
    repository.expected = sample_columns()
    service = ScanService(repository, collector_factory(StubCollector(sample_columns())))

    report = service.run_scan("game", ScanTrigger.SCHEDULED)

    assert report.baseline_created is False
    assert report.changes == ()
    assert repository.status is ScanStatus.COMPLETED


def test_logging_failure_does_not_change_completed_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from schema_sentry.application import scan_service as scan_service_module

    repository = FakeScanRepository()
    service = ScanService(repository, collector_factory(StubCollector(sample_columns())))

    def fail_to_write_log(_event: str, **_fields: object) -> None:
        raise OSError("log sink unavailable")

    monkeypatch.setattr(scan_service_module.logger, "info", fail_to_write_log)

    report = service.run_scan("game", ScanTrigger.MANUAL)

    assert report.baseline_created is True
    assert repository.status is ScanStatus.COMPLETED


def test_collection_failure_records_sanitized_failure() -> None:
    repository = FakeScanRepository()
    service = ScanService(repository, collector_factory(FailingCollector()))

    with pytest.raises(ConnectionError, match="must-not-be-persisted"):
        service.run_scan("game", ScanTrigger.MANUAL)

    assert repository.status is ScanStatus.FAILED
    assert repository.error == ("ConnectionError", "schema collection failed")


def test_collection_failure_emits_sanitized_structured_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from schema_sentry.logging import configure_logging

    repository = FakeScanRepository()
    service = ScanService(repository, collector_factory(FailingCollector()))
    configure_logging("INFO")

    with pytest.raises(ConnectionError):
        service.run_scan("game", ScanTrigger.MANUAL)

    captured = capsys.readouterr().out
    event = json.loads(captured)
    assert event["event"] == "source_connection_failed"
    assert event["source_key"] == "game"
    assert event["scan_id"] == str(repository.scan_id)
    assert event["status"] == "FAILED"
    assert "must-not-be-persisted" not in captured


def test_empty_snapshot_is_failed_instead_of_promoted() -> None:
    repository = FakeScanRepository()
    service = ScanService(repository, collector_factory(StubCollector(())))

    with pytest.raises(EmptySchemaSnapshot, match="game"):
        service.run_scan("game", ScanTrigger.MANUAL)

    assert repository.expected == ()
    assert repository.status is ScanStatus.FAILED


def test_concurrent_scan_is_rejected_before_collection() -> None:
    repository = FakeScanRepository(lock_acquired=False)
    service = ScanService(repository, collector_factory(StubCollector(sample_columns())))

    with pytest.raises(ScanAlreadyRunning, match="game"):
        service.run_scan("game", ScanTrigger.MANUAL)

    assert repository.status is None
