from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from schema_sentry.infrastructure.db.models import AlertDeliveryModel


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, delivery: AlertDeliveryModel) -> AlertDeliveryModel:
        self.session.add(delivery)
        self.session.flush()
        return delivery

    def list_for_scan(self, scan_id: UUID) -> tuple[AlertDeliveryModel, ...]:
        statement = (
            select(AlertDeliveryModel)
            .where(AlertDeliveryModel.scan_id == scan_id)
            .order_by(AlertDeliveryModel.created_at, AlertDeliveryModel.id)
        )
        return tuple(self.session.scalars(statement))
