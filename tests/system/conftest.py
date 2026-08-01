import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (
    "docker",
    "compose",
    "-p",
    "schema-sentry-demo",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.demo.yml",
)
METADATA_URL = (
    "postgresql+psycopg://schema_sentry:schema_sentry_dev@localhost:56433/"
    "schema_sentry_demo"
)
SOURCE_ADMIN_URL = (
    "postgresql://game_admin:game_admin_dev@localhost:56432/game_source_demo"
)


@pytest.fixture(scope="session", autouse=True)
def isolated_system_stack() -> Iterator[None]:
    subprocess.run(
        [*COMPOSE, "up", "-d", "source-db", "metadata-db", "mailpit"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [*COMPOSE, "run", "--rm", "api", ".venv/bin/alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
    )
    try:
        yield
    finally:
        subprocess.run(
            [*COMPOSE, "down", "--volumes", "--remove-orphans"],
            cwd=ROOT,
            check=True,
        )


@pytest.fixture
def system_session() -> Iterator[Session]:
    subprocess.run([*COMPOSE, "stop", "api"], cwd=ROOT, check=False)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", METADATA_URL)
    engine = create_engine(METADATA_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    try:
        with Session(engine) as session:
            yield session
            session.rollback()
    finally:
        command.downgrade(config, "base")
        engine.dispose()


@pytest.fixture
def system_source_schema() -> Iterator[None]:
    with psycopg.connect(SOURCE_ADMIN_URL, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS mart.daily_revenue CASCADE")
        connection.execute("DROP TABLE IF EXISTS public.purchases CASCADE")
        connection.execute("DROP TABLE IF EXISTS public.sessions CASCADE")
        connection.execute("DROP TABLE IF EXISTS public.matches CASCADE")
        connection.execute("DROP TABLE IF EXISTS public.players CASCADE")
        connection.execute(Path("demo/sql/001_game_schema.sql").read_text())
    try:
        yield
    finally:
        with psycopg.connect(SOURCE_ADMIN_URL, autocommit=True) as connection:
            connection.execute(Path("demo/sql/011_restore_schema.sql").read_text())
