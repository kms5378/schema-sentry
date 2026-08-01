from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from schema_sentry.domain.enums import ChangeState
from schema_sentry.infrastructure.db.models import SchemaChangeModel


class ChangeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, change: SchemaChangeModel) -> SchemaChangeModel:
        self.session.add(change)
        self.session.flush()
        return change

    def find_open(self, source_id: UUID, fingerprint: str) -> SchemaChangeModel | None:
        return self.session.scalar(
            select(SchemaChangeModel).where(
                SchemaChangeModel.source_id == source_id,
                SchemaChangeModel.fingerprint == fingerprint,
                SchemaChangeModel.state == ChangeState.OPEN,
            )
        )

    def list_open_for_source(self, source_id: UUID) -> tuple[SchemaChangeModel, ...]:
        statement = (
            select(SchemaChangeModel)
            .where(
                SchemaChangeModel.source_id == source_id,
                SchemaChangeModel.state == ChangeState.OPEN,
            )
            .order_by(SchemaChangeModel.created_at, SchemaChangeModel.id)
        )
        return tuple(self.session.scalars(statement))
