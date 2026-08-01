from dataclasses import dataclass

from sqlalchemy.orm import Session

from schema_sentry.infrastructure.db.repositories.alerts import AlertRepository
from schema_sentry.infrastructure.db.repositories.catalog import CatalogRepository
from schema_sentry.infrastructure.db.repositories.changes import ChangeRepository
from schema_sentry.infrastructure.db.repositories.scans import ScanRepository


@dataclass(frozen=True, slots=True)
class RepositoryBundle:
    scans: ScanRepository
    catalog: CatalogRepository
    changes: ChangeRepository
    alerts: AlertRepository

    @classmethod
    def from_session(cls, session: Session) -> "RepositoryBundle":
        return cls(
            scans=ScanRepository(session),
            catalog=CatalogRepository(session),
            changes=ChangeRepository(session),
            alerts=AlertRepository(session),
        )


__all__ = [
    "AlertRepository",
    "CatalogRepository",
    "ChangeRepository",
    "RepositoryBundle",
    "ScanRepository",
]
