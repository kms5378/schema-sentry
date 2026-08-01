import json
from uuid import uuid4

import pytest

from schema_sentry.application.validation_service import BlockingChange, ValidationService
from schema_sentry.domain.enums import ChangeType, Severity
from schema_sentry.domain.models import DatasetRef


class FakeValidationRepository:
    def __init__(self, changes: tuple[BlockingChange, ...]) -> None:
        self.changes = changes

    def list_open_breaking_changes_for_pipeline(
        self, pipeline_key: str
    ) -> tuple[BlockingChange, ...]:
        return self.changes


def test_open_breaking_change_blocks_pipeline() -> None:
    blocking = BlockingChange(
        id=uuid4(),
        dataset=DatasetRef("public", "purchases"),
        column_name="amount",
        change_type=ChangeType.TYPE_CHANGE,
        severity=Severity.BREAKING,
    )

    result = ValidationService(FakeValidationRepository((blocking,))).validate_pipeline(
        "daily_revenue"
    )

    assert result.safe is False
    assert result.blocking_changes == (blocking,)


def test_pipeline_without_open_breaking_change_is_safe() -> None:
    result = ValidationService(FakeValidationRepository(())).validate_pipeline("daily_revenue")

    assert result.safe is True
    assert result.blocking_changes == ()


def test_validation_emits_structured_pipeline_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from schema_sentry.logging import configure_logging

    configure_logging("INFO")

    ValidationService(FakeValidationRepository(())).validate_pipeline("daily_revenue")

    event = json.loads(capsys.readouterr().out)
    assert event["event"] == "pipeline_validation_completed"
    assert event["pipeline_key"] == "daily_revenue"
    assert event["status"] == "SAFE"
    assert isinstance(event["duration_ms"], int)
