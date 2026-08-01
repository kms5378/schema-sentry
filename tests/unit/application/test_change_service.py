from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest

from schema_sentry.application.change_service import (
    BaselineVersionConflict,
    ChangeNotFound,
    ChangeService,
)


class FakeLockedAcceptance:
    def __init__(self, baseline_version: int) -> None:
        self.baseline_version = baseline_version
        self.applied = False

    def apply(self) -> int:
        self.applied = True
        self.baseline_version += 1
        return self.baseline_version


class FakeChangeRepository:
    def __init__(self, locked: FakeLockedAcceptance | None) -> None:
        self.locked = locked

    @contextmanager
    def acceptance_transaction(self, change_id: UUID) -> Iterator[FakeLockedAcceptance | None]:
        yield self.locked


def test_accept_updates_baseline_and_returns_new_version() -> None:
    change_id = uuid4()
    locked = FakeLockedAcceptance(baseline_version=7)

    result = ChangeService(FakeChangeRepository(locked)).accept(
        change_id, expected_baseline_version=7
    )

    assert result.change_id == change_id
    assert result.baseline_version == 8
    assert locked.applied is True


def test_stale_acceptance_is_rejected_without_mutation() -> None:
    locked = FakeLockedAcceptance(baseline_version=7)

    with pytest.raises(BaselineVersionConflict) as error:
        ChangeService(FakeChangeRepository(locked)).accept(uuid4(), expected_baseline_version=6)

    assert error.value.expected == 6
    assert error.value.actual == 7
    assert locked.applied is False


def test_missing_change_is_reported() -> None:
    with pytest.raises(ChangeNotFound):
        ChangeService(FakeChangeRepository(None)).accept(uuid4(), expected_baseline_version=1)
