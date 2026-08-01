from schema_sentry.domain.diff import diff_columns
from schema_sentry.domain.enums import ChangeType, Severity
from schema_sentry.domain.models import (
    ColumnDefinition,
    ColumnRef,
    DatasetRef,
)
from schema_sentry.domain.type_rules import parse_postgres_type

PURCHASES = DatasetRef(schema="public", table="purchases")


def column(
    name: str,
    data_type: str = "integer",
    *,
    nullable: bool = True,
) -> ColumnDefinition:
    return ColumnDefinition(
        dataset=PURCHASES,
        name=name,
        data_type=parse_postgres_type(data_type),
        nullable=nullable,
        default=None,
    )


def test_nullable_addition_is_informational() -> None:
    changes = diff_columns([], [column("coupon_code", "text")])

    assert len(changes) == 1
    assert changes[0].change_type is ChangeType.ADD_COLUMN
    assert changes[0].severity is Severity.INFO


def test_required_addition_is_warning() -> None:
    changes = diff_columns([], [column("currency", "text", nullable=False)])

    assert changes[0].severity is Severity.WARNING


def test_drop_dependency_is_breaking() -> None:
    amount = column("amount", "numeric(12,2)", nullable=False)

    changes = diff_columns([amount], [], dependencies=[amount.ref])

    assert changes[0].change_type is ChangeType.DROP_COLUMN
    assert changes[0].severity is Severity.BREAKING


def test_drop_without_dependency_is_warning() -> None:
    changes = diff_columns([column("legacy_code")], [])

    assert changes[0].severity is Severity.WARNING


def test_incompatible_type_change_is_breaking() -> None:
    changes = diff_columns(
        [column("amount", "numeric(12,2)")],
        [column("amount", "character varying")],
    )

    assert changes[0].change_type is ChangeType.TYPE_CHANGE
    assert changes[0].severity is Severity.BREAKING


def test_nullable_dependency_change_is_breaking() -> None:
    before = column("amount", "numeric(12,2)", nullable=False)
    after = column("amount", "numeric(12,2)", nullable=True)

    changes = diff_columns([before], [after], dependencies=[ColumnRef(PURCHASES, "amount")])

    assert changes[0].change_type is ChangeType.NULLABILITY_CHANGE
    assert changes[0].severity is Severity.BREAKING


def test_change_output_is_deterministic() -> None:
    changes = diff_columns([], [column("zeta"), column("alpha")])

    assert [change.column_name for change in changes] == ["alpha", "zeta"]
