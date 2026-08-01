from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from schema_sentry.application.change_service import ChangeService
from schema_sentry.application.query_service import ScanQueryService
from schema_sentry.application.scan_service import ScanService
from schema_sentry.application.validation_service import ValidationService
from schema_sentry.config import Settings, get_settings
from schema_sentry.infrastructure.db.postgres_collector import PostgresSchemaCollector
from schema_sentry.infrastructure.db.repositories.changes import ChangeRepository
from schema_sentry.infrastructure.db.repositories.scans import (
    ScanQueryRepository,
    SqlAlchemyScanRepository,
)
from schema_sentry.infrastructure.db.session import create_session_factory


@lru_cache(maxsize=8)
def _session_factory(database_url: str) -> sessionmaker[Session]:
    return create_session_factory(database_url)


def get_database_session(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[Session]:
    factory = _session_factory(settings.metadata_database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except HTTPException:
        session.commit()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_scan_service(
    session: Annotated[Session, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScanService:
    repository = SqlAlchemyScanRepository(session)
    return ScanService(
        repository,
        lambda _: PostgresSchemaCollector(settings.source_database_url),
    )


def get_change_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> ChangeService:
    return ChangeService(ChangeRepository(session))


def get_validation_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> ValidationService:
    return ValidationService(ChangeRepository(session))


def get_scan_query_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> ScanQueryService:
    return ScanQueryService(ScanQueryRepository(session))


class ReadinessChecker:
    def __init__(self, session: Session) -> None:
        self.session = session

    def check(self) -> bool:
        try:
            database_revision = self.session.scalar(text("SELECT version_num FROM alembic_version"))
            expected_revision = ScriptDirectory.from_config(
                Config("alembic.ini")
            ).get_current_head()
            return bool(database_revision and database_revision == expected_revision)
        except (OSError, SQLAlchemyError):
            self.session.rollback()
            return False


def get_readiness_checker(
    session: Annotated[Session, Depends(get_database_session)],
) -> ReadinessChecker:
    return ReadinessChecker(session)
