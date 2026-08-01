import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command

INTEGRATION_DATABASE_URL = os.getenv(
    "SCHEMA_SENTRY_INTEGRATION_DATABASE_URL",
    "postgresql+psycopg://schema_sentry:schema_sentry_dev@localhost:55433/schema_sentry",
)
SOURCE_DATABASE_URL = os.getenv(
    "SCHEMA_SENTRY_SOURCE_DATABASE_URL",
    "postgresql+psycopg://schema_sentry_reader:source_reader_dev@localhost:55432/game_source",
)
SOURCE_ADMIN_DATABASE_URL = os.getenv(
    "SCHEMA_SENTRY_SOURCE_ADMIN_DATABASE_URL",
    "postgresql://game_admin:game_admin_dev@localhost:55432/game_source",
)


@pytest.fixture(scope="session")
def metadata_engine() -> Iterator[Engine]:
    engine = create_engine(INTEGRATION_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", INTEGRATION_DATABASE_URL)
    return config


@pytest.fixture
def empty_repository(alembic_config: Config) -> Iterator[None]:
    command.downgrade(alembic_config, "base")
    yield
    command.downgrade(alembic_config, "base")


@pytest.fixture
def migrated_engine(
    alembic_config: Config,
    metadata_engine: Engine,
    empty_repository: None,
) -> Engine:
    command.upgrade(alembic_config, "head")
    return metadata_engine


@pytest.fixture
def session(migrated_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    with factory() as database_session:
        yield database_session
        database_session.rollback()


@pytest.fixture(scope="session")
def source_database_url() -> str:
    return SOURCE_DATABASE_URL


@pytest.fixture
def game_source_schema() -> Iterator[None]:
    setup_sql = Path("demo/sql/001_game_schema.sql").read_text()
    with psycopg.connect(SOURCE_ADMIN_DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS mart.daily_revenue CASCADE")
        connection.execute("DROP TABLE IF EXISTS public.purchases CASCADE")
        connection.execute("DROP TABLE IF EXISTS public.sessions CASCADE")
        connection.execute("DROP TABLE IF EXISTS public.matches CASCADE")
        connection.execute("DROP TABLE IF EXISTS public.players CASCADE")
        connection.execute(setup_sql)
    yield
