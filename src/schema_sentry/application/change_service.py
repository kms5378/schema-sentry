from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class ChangeNotFound(LookupError):
    def __init__(self, change_id: UUID) -> None:
        super().__init__(f"schema change not found: {change_id}")


class BaselineVersionConflict(RuntimeError):
    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"baseline version conflict: expected={expected} actual={actual}")


class LockedAcceptance(Protocol):
    baseline_version: int

    def apply(self) -> int: ...


class ChangePersistence(Protocol):
    def acceptance_transaction(
        self, change_id: UUID
    ) -> AbstractContextManager[LockedAcceptance | None]: ...


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    change_id: UUID
    baseline_version: int


class ChangeService:
    def __init__(self, repository: ChangePersistence) -> None:
        self.repository = repository

    def accept(self, change_id: UUID, expected_baseline_version: int) -> AcceptanceResult:
        with self.repository.acceptance_transaction(change_id) as locked:
            if locked is None:
                raise ChangeNotFound(change_id)
            if locked.baseline_version != expected_baseline_version:
                raise BaselineVersionConflict(expected_baseline_version, locked.baseline_version)
            return AcceptanceResult(change_id=change_id, baseline_version=locked.apply())
