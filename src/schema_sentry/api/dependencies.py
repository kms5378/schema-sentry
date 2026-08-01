from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from schema_sentry.application.change_service import ChangeService
from schema_sentry.application.notification_service import NotificationService, Notifier
from schema_sentry.application.query_service import ScanQueryService
from schema_sentry.application.scan_service import ScanService
from schema_sentry.application.validation_service import ValidationService
from schema_sentry.config import Settings, get_settings
from schema_sentry.domain.enums import AlertChannel
from schema_sentry.infrastructure.db.postgres_collector import PostgresSchemaCollector
from schema_sentry.infrastructure.db.repositories.alerts import AlertRepository
from schema_sentry.infrastructure.db.repositories.changes import ChangeRepository
from schema_sentry.infrastructure.db.repositories.scans import (
    ScanQueryRepository,
    SqlAlchemyScanRepository,
)
from schema_sentry.infrastructure.db.session import create_session_factory, session_scope
from schema_sentry.infrastructure.notifications.email import EmailNotifier
from schema_sentry.infrastructure.notifications.slack import SlackNotifier

logger = structlog.get_logger(__name__)


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
    repository = SqlAlchemyScanRepository(session, alert_channels=_enabled_channels(settings))
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


def _enabled_channels(settings: Settings) -> tuple[AlertChannel, ...]:
    channels: list[AlertChannel] = []
    if settings.slack_webhook_url and settings.slack_webhook_url.get_secret_value():
        channels.append(AlertChannel.SLACK)
    if settings.email_to:
        channels.append(AlertChannel.EMAIL)
    return tuple(channels)


def _notifiers(settings: Settings) -> tuple[Notifier, ...]:
    notifiers: list[Notifier] = []
    if settings.slack_webhook_url and settings.slack_webhook_url.get_secret_value():
        notifiers.append(SlackNotifier(settings.slack_webhook_url.get_secret_value()))
    if settings.email_to:
        notifiers.append(
            EmailNotifier(
                host=settings.smtp_host,
                port=settings.smtp_port,
                sender=settings.email_from,
                recipients=settings.email_to,
            )
        )
    return tuple(notifiers)


def get_notification_service(
    session: Annotated[Session, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationService:
    return NotificationService(
        AlertRepository(session),
        _notifiers(settings),
        dashboard_base_url=str(settings.dashboard_base_url),
    )


class NotificationDispatcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def dispatch_scan(self, scan_id: UUID) -> None:
        try:
            factory = _session_factory(self.settings.metadata_database_url)
            with session_scope(factory) as session:
                NotificationService(
                    AlertRepository(session),
                    _notifiers(self.settings),
                    dashboard_base_url=str(self.settings.dashboard_base_url),
                ).dispatch_scan(scan_id)
        except Exception:
            logger.exception("notification_dispatch_failed", scan_id=str(scan_id))

    def dispatch_system_error(self, source_key: str) -> None:
        try:
            factory = _session_factory(self.settings.metadata_database_url)
            with session_scope(factory) as session:
                repository = AlertRepository(session)
                scan_id = repository.latest_failed_scan_id(source_key)
                if scan_id is None:
                    return
                NotificationService(
                    repository,
                    _notifiers(self.settings),
                    dashboard_base_url=str(self.settings.dashboard_base_url),
                ).dispatch_system_error(scan_id)
        except Exception:
            logger.exception("system_notification_dispatch_failed", source_key=source_key)


def get_notification_dispatcher(
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationDispatcher:
    return NotificationDispatcher(settings)


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
