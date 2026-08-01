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
