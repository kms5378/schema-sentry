import pytest

from schema_sentry.infrastructure.db.postgres_collector import PostgresSchemaCollector


def test_collector_reads_game_columns(source_database_url: str, game_source_schema: None) -> None:
    columns = PostgresSchemaCollector(source_database_url).collect()
    amount = next(
        column
        for column in columns
        if column.dataset.schema == "public"
        and column.dataset.table == "purchases"
        and column.name == "amount"
    )

    assert amount.data_type.render() == "numeric(12,2)"
    assert amount.nullable is False
    assert amount.ordinal == 4
    assert {column.dataset.schema for column in columns} == {"public", "mart"}


@pytest.mark.parametrize("schema", ["*", "pub%"])
def test_collector_rejects_wildcard_schemas(source_database_url: str, schema: str) -> None:
    with pytest.raises(ValueError, match="literal schema"):
        PostgresSchemaCollector(source_database_url, included_schemas=(schema,))
