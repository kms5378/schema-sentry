from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from schema_sentry.api.app import create_app
from schema_sentry.api.dependencies import (
    get_change_service,
    get_readiness_checker,
    get_scan_query_service,
    get_scan_service,
    get_validation_service,
)
from schema_sentry.application.change_service import AcceptanceResult
from schema_sentry.application.query_service import PersistedScan
from schema_sentry.application.scan_service import ScanReport
from schema_sentry.application.validation_service import PipelineValidation
from schema_sentry.config import Settings, get_settings
from schema_sentry.domain.enums import ScanStatus, ScanTrigger

API_KEY = "contract-test-api-key"
SCAN_ID = uuid4()


class FakeScanService:
    def __init__(self) -> None:
        self.error: Exception | None = None

    def run_scan(self, source_key: str, trigger: ScanTrigger) -> ScanReport:
        if self.error:
            raise self.error
        return ScanReport(
            scan_id=SCAN_ID,
            source_key=source_key,
            trigger=trigger,
            baseline_created=False,
            observed_count=16,
            changes=(),
        )


class FakeChangeService:
    def __init__(self) -> None:
        self.error: Exception | None = None

    def accept(self, change_id: UUID, expected_baseline_version: int) -> AcceptanceResult:
        if self.error:
            raise self.error
        return AcceptanceResult(change_id, expected_baseline_version + 1)


class FakeValidationService:
    def __init__(self) -> None:
        self.result = PipelineValidation("daily_revenue", True, ())

    def validate_pipeline(self, pipeline_key: str) -> PipelineValidation:
        return self.result


class FakeScanQueryService:
    def __init__(self) -> None:
        self.result: PersistedScan | None = PersistedScan(
            id=SCAN_ID,
            source_key="game",
            trigger=ScanTrigger.MANUAL,
            status=ScanStatus.COMPLETED,
            started_at=datetime(2026, 8, 1, tzinfo=UTC),
            finished_at=datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
            duration_ms=1000,
            error_code=None,
            error_message=None,
            changes=(),
        )

    def latest(self) -> PersistedScan | None:
        return self.result

    def get(self, scan_id: UUID) -> PersistedScan | None:
        return self.result if self.result and scan_id == self.result.id else None


class FakeReadinessChecker:
    def __init__(self) -> None:
        self.ready = True

    def check(self) -> bool:
        return self.ready


@dataclass
class ApiFakes:
    scan: FakeScanService
    change: FakeChangeService
    validation: FakeValidationService
    query: FakeScanQueryService
    readiness: FakeReadinessChecker


@pytest.fixture
def api_fakes() -> ApiFakes:
    return ApiFakes(
        scan=FakeScanService(),
        change=FakeChangeService(),
        validation=FakeValidationService(),
        query=FakeScanQueryService(),
        readiness=FakeReadinessChecker(),
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        metadata_database_url="postgresql+psycopg://unused",
        source_database_url="postgresql+psycopg://unused",
        api_key=SecretStr(API_KEY),
    )


@pytest.fixture
def client(api_fakes: ApiFakes, settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_scan_service] = lambda: api_fakes.scan
    app.dependency_overrides[get_change_service] = lambda: api_fakes.change
    app.dependency_overrides[get_validation_service] = lambda: api_fakes.validation
    app.dependency_overrides[get_scan_query_service] = lambda: api_fakes.query
    app.dependency_overrides[get_readiness_checker] = lambda: api_fakes.readiness
    return TestClient(app)


@pytest.fixture
def api_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}
