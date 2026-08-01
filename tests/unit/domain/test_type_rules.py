import pytest

from schema_sentry.domain.enums import Severity
from schema_sentry.domain.type_rules import (
    canonicalize_postgres_type,
    classify_type_change,
    parse_postgres_type,
)


@pytest.mark.parametrize(
    ("before", "after", "severity"),
    [
        ("integer", "bigint", Severity.WARNING),
        ("smallint", "integer", Severity.WARNING),
        ("numeric(12,2)", "character varying", Severity.BREAKING),
        ("character varying(50)", "character varying(20)", Severity.BREAKING),
        ("character varying(20)", "character varying(50)", Severity.WARNING),
        ("numeric(12,2)", "numeric(18,2)", Severity.WARNING),
        ("numeric(12,2)", "numeric(10,2)", Severity.BREAKING),
        ("numeric(12,2)", "numeric", Severity.WARNING),
        ("numeric", "numeric(12,2)", Severity.BREAKING),
    ],
)
def test_type_change_policy(before: str, after: str, severity: Severity) -> None:
    assessment = classify_type_change(parse_postgres_type(before), parse_postgres_type(after))

    assert assessment.severity is severity


def test_postgres_aliases_share_one_canonical_form() -> None:
    assert parse_postgres_type("int4") == parse_postgres_type("integer")
    assert parse_postgres_type("varchar(50)").render() == "character varying(50)"


def test_information_schema_varchar_keeps_length() -> None:
    actual = canonicalize_postgres_type("character varying", "varchar", 50, None, None)

    assert actual.render() == "character varying(50)"


def test_information_schema_user_defined_type_uses_udt_name() -> None:
    actual = canonicalize_postgres_type("USER-DEFINED", "citext", None, None, None)

    assert actual.render() == "citext"
