from uuid import uuid4

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
