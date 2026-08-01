import os

import psycopg
import pytest


def test_source_reader_cannot_create_tables() -> None:
    database_url = os.environ["SCHEMA_SENTRY_SOURCE_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1
    )

    with (
        psycopg.connect(database_url) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("CREATE TABLE public.forbidden(id integer)")


def test_pipeline_role_has_only_required_read_and_write_access(
    game_source_schema: None,
    pipeline_database_url: str,
) -> None:
    with psycopg.connect(pipeline_database_url) as connection:
        assert connection.execute("SELECT COUNT(*) FROM public.purchases").fetchone() == (3,)
        connection.execute(
            """
            INSERT INTO mart.daily_revenue (date, revenue)
            VALUES ('2026-08-01', 2000.00)
            ON CONFLICT (date) DO UPDATE SET revenue = EXCLUDED.revenue
            """
        )

    with (
        psycopg.connect(pipeline_database_url) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("DROP TABLE public.purchases")
