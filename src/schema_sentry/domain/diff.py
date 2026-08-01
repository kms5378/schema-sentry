from collections.abc import Collection, Sequence

from schema_sentry.domain.enums import ChangeType, Severity
from schema_sentry.domain.models import ColumnDefinition, ColumnRef, SchemaChange
from schema_sentry.domain.type_rules import classify_type_change


def _change(
    change_type: ChangeType,
    severity: Severity,
    before: ColumnDefinition | None,
    after: ColumnDefinition | None,
) -> SchemaChange:
    column = before or after
    if column is None:
        raise ValueError("schema change requires a before or after column")
    return SchemaChange(
        dataset=column.dataset,
        column_name=column.name,
        change_type=change_type,
        severity=severity,
        before=before,
        after=after,
    )


def compare_column(
    ref: ColumnRef,
    before: ColumnDefinition | None,
    after: ColumnDefinition | None,
    dependencies: Collection[ColumnRef],
) -> tuple[SchemaChange, ...]:
    if before is None and after is not None:
        severity = Severity.INFO if after.nullable else Severity.WARNING
        return (_change(ChangeType.ADD_COLUMN, severity, before, after),)
    if before is not None and after is None:
        severity = Severity.BREAKING if ref in dependencies else Severity.WARNING
        return (_change(ChangeType.DROP_COLUMN, severity, before, after),)
    if before is None or after is None:
        return ()

    changes: list[SchemaChange] = []
    if before.data_type != after.data_type:
        assessment = classify_type_change(before.data_type, after.data_type)
        changes.append(_change(ChangeType.TYPE_CHANGE, assessment.severity, before, after))
    if before.nullable != after.nullable:
        severity = (
            Severity.BREAKING
            if not before.nullable and after.nullable and ref in dependencies
            else Severity.WARNING
        )
        changes.append(_change(ChangeType.NULLABILITY_CHANGE, severity, before, after))
    return tuple(changes)


def change_sort_key(change: SchemaChange) -> tuple[str, str, str, str]:
    return (
        change.dataset.schema,
        change.dataset.table,
        change.column_name,
        change.change_type.value,
    )


def diff_columns(
    expected: Sequence[ColumnDefinition],
    observed: Sequence[ColumnDefinition],
    dependencies: Collection[ColumnRef] = (),
) -> tuple[SchemaChange, ...]:
    expected_by_ref = {column.ref: column for column in expected}
    observed_by_ref = {column.ref: column for column in observed}
    dependency_set = set(dependencies)
    changes: list[SchemaChange] = []

    for ref in sorted(expected_by_ref.keys() | observed_by_ref.keys()):
        changes.extend(
            compare_column(
                ref,
                expected_by_ref.get(ref),
                observed_by_ref.get(ref),
                dependency_set,
            )
        )

    return tuple(sorted(changes, key=change_sort_key))
