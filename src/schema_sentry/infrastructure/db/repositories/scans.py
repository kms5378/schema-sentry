from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from schema_sentry.infrastructure.db.models import ScanRunModel


class ScanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, scan: ScanRunModel) -> ScanRunModel:
        self.session.add(scan)
        self.session.flush()
        return scan

    def get(self, scan_id: UUID) -> ScanRunModel | None:
        return self.session.get(ScanRunModel, scan_id)

    def latest_for_source(self, source_id: UUID) -> ScanRunModel | None:
        statement = (
            select(ScanRunModel)
            .where(ScanRunModel.source_id == source_id)
            .order_by(ScanRunModel.started_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)
