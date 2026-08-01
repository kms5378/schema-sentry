from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schema_sentry.infrastructure.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class DataSourceModel(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "data_sources"

    key: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    connection_ref: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    baseline_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    datasets: Mapped[list["DatasetModel"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class DatasetModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("source_id", "schema_name", "table_name", name="dataset_identity"),
    )

    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"))
    schema_name: Mapped[str] = mapped_column(String(63))
    table_name: Mapped[str] = mapped_column(String(63))
    owner: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(1000))

    source: Mapped[DataSourceModel] = relationship(back_populates="datasets")
    expected_columns: Mapped[list["ExpectedColumnModel"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class ExpectedColumnModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "expected_columns"
    __table_args__ = (UniqueConstraint("dataset_id", "name", name="expected_column_identity"),)

    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(63))
    data_type_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    nullable: Mapped[bool] = mapped_column(Boolean)
    default_expression: Mapped[str | None] = mapped_column("default", String(1000))
    ordinal: Mapped[int] = mapped_column(Integer)

    dataset: Mapped[DatasetModel] = relationship(back_populates="expected_columns")
