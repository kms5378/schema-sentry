from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from schema_sentry.infrastructure.db.models import (
    DatasetModel,
    DataSourceModel,
    ExpectedColumnModel,
)


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_source(self, source: DataSourceModel) -> DataSourceModel:
        self.session.add(source)
        self.session.flush()
        return source

    def get_source_by_key(self, key: str) -> DataSourceModel | None:
        return self.session.scalar(select(DataSourceModel).where(DataSourceModel.key == key))

    def add_dataset(self, dataset: DatasetModel) -> DatasetModel:
        self.session.add(dataset)
        self.session.flush()
        return dataset

    def get_dataset(self, source_id: UUID, schema: str, table: str) -> DatasetModel | None:
        return self.session.scalar(
            select(DatasetModel).where(
                DatasetModel.source_id == source_id,
                DatasetModel.schema_name == schema,
                DatasetModel.table_name == table,
            )
        )

    def add_expected_column(self, column: ExpectedColumnModel) -> ExpectedColumnModel:
        self.session.add(column)
        self.session.flush()
        return column

    def list_expected_columns(self, dataset_id: UUID) -> tuple[ExpectedColumnModel, ...]:
        statement = (
            select(ExpectedColumnModel)
            .where(ExpectedColumnModel.dataset_id == dataset_id)
            .order_by(ExpectedColumnModel.ordinal)
        )
        return tuple(self.session.scalars(statement))
