from dataclasses import dataclass
from typing import Any

from schema_sentry.domain.enums import ChangeType, Severity


@dataclass(frozen=True, order=True, slots=True)
class DatasetRef:
    schema: str
    table: str

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.table}"


@dataclass(frozen=True, order=True, slots=True)
class ColumnRef:
    dataset: DatasetRef
    name: str

    @property
    def qualified_name(self) -> str:
        return f"{self.dataset.qualified_name}.{self.name}"


@dataclass(frozen=True, slots=True)
class CanonicalType:
    name: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None

    def render(self) -> str:
        if self.length is not None:
            return f"{self.name}({self.length})"
        if self.precision is not None and self.scale is not None:
            return f"{self.name}({self.precision},{self.scale})"
        if self.precision is not None:
            return f"{self.name}({self.precision})"
        return self.name

    def to_canonical_dict(self) -> dict[str, int | str | None]:
        return {
            "name": self.name,
            "length": self.length,
            "precision": self.precision,
            "scale": self.scale,
        }


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    dataset: DatasetRef
    name: str
    data_type: CanonicalType
    nullable: bool
    default: str | None
    ordinal: int = 0

    @property
    def ref(self) -> ColumnRef:
        return ColumnRef(self.dataset, self.name)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset.qualified_name,
            "name": self.name,
            "data_type": self.data_type.to_canonical_dict(),
            "nullable": self.nullable,
            "default": self.default,
        }


@dataclass(frozen=True, slots=True)
class SchemaChange:
    dataset: DatasetRef
    column_name: str
    change_type: ChangeType
    severity: Severity
    before: ColumnDefinition | None
    after: ColumnDefinition | None

    @property
    def ref(self) -> ColumnRef:
        return ColumnRef(self.dataset, self.column_name)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset.qualified_name,
            "column_name": self.column_name,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "before": self.before.to_canonical_dict() if self.before else None,
            "after": self.after.to_canonical_dict() if self.after else None,
        }
