from schema_sentry.domain.diff import diff_columns
from schema_sentry.domain.fingerprint import change_fingerprint
from schema_sentry.domain.models import ColumnDefinition, DatasetRef
from schema_sentry.domain.type_rules import parse_postgres_type


def make_column(data_type: str) -> ColumnDefinition:
    return ColumnDefinition(
        dataset=DatasetRef("public", "purchases"),
        name="amount",
        data_type=parse_postgres_type(data_type),
        nullable=False,
        default=None,
    )


def test_fingerprint_is_stable_for_equivalent_change() -> None:
    first = diff_columns([make_column("numeric(12,2)")], [make_column("varchar")])[0]
    second = diff_columns([make_column("numeric(12,2)")], [make_column("character varying")])[0]

    assert change_fingerprint("game", first) == change_fingerprint("game", second)


def test_fingerprint_changes_with_source() -> None:
    change = diff_columns([make_column("numeric(12,2)")], [make_column("varchar")])[0]

    assert change_fingerprint("game", change) != change_fingerprint("billing", change)
