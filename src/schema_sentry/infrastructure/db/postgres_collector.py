from typing import Any

import psycopg
from psycopg.rows import dict_row

from schema_sentry.domain.models import ColumnDefinition, DatasetRef
from schema_sentry.domain.type_rules import canonicalize_postgres_type

COLLECT_COLUMNS_SQL = """
SELECT table_schema, table_name, column_name, ordinal_position,
       is_nullable, data_type, udt_name, character_maximum_length,
       numeric_precision, numeric_scale, column_default
FROM information_schema.columns
WHERE table_schema = ANY(%s)
ORDER BY table_schema, table_name, ordinal_position
"""


class PostgresSchemaCollector:
    def __init__(
        self,
        database_url: str,
        included_schemas: tuple[str, ...] = ("public", "mart"),
    ) -> None:
        if not included_schemas or any(
            wildcard in schema for schema in included_schemas for wildcard in ("*", "%")
        ):
            raise ValueError("included_schemas must contain literal schema names")
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.included_schemas = included_schemas

    def collect(self) -> tuple[ColumnDefinition, ...]:
        with psycopg.connect(
            self.database_url,
            connect_timeout=3,
            options="-c statement_timeout=5000 -c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as connection:
            rows = connection.execute(
                COLLECT_COLUMNS_SQL, (list(self.included_schemas),)
            ).fetchall()
        return tuple(self._to_column(row) for row in rows)

    @staticmethod
    def _to_column(row: dict[str, Any]) -> ColumnDefinition:
        return ColumnDefinition(
            dataset=DatasetRef(schema=row["table_schema"], table=row["table_name"]),
            name=row["column_name"],
            data_type=canonicalize_postgres_type(
                data_type=row["data_type"],
                udt_name=row["udt_name"],
                character_maximum_length=row["character_maximum_length"],
                numeric_precision=row["numeric_precision"],
                numeric_scale=row["numeric_scale"],
            ),
            nullable=row["is_nullable"] == "YES",
            default=row["column_default"],
            ordinal=row["ordinal_position"],
        )
