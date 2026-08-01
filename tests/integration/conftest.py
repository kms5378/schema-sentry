import os
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command

INTEGRATION_DATABASE_URL = os.getenv(
    "SCHEMA_SENTRY_INTEGRATION_DATABASE_URL",
    "postgresql+psycopg://schema_sentry:schema_sentry_dev@localhost:55433/schema_sentry",
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
