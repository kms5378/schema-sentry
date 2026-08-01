from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schema_sentry.domain.enums import (
    ChangeState,
    ChangeType,
    ScanStatus,
    ScanTrigger,
    Severity,
)
from schema_sentry.infrastructure.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from schema_sentry.infrastructure.db.models.catalog import DatasetModel, DataSourceModel


class ScanRunModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scan_runs"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"))
    trigger: Mapped[ScanTrigger] = mapped_column(
        Enum(ScanTrigger, native_enum=False, create_constraint=True, name="scan_trigger")
    )
    status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, native_enum=False, create_constraint=True, name="scan_status")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)

    source: Mapped[DataSourceModel] = relationship()
    observed_columns: Mapped[list["ObservedColumnModel"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class ObservedColumnModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "observed_columns"

    scan_id: Mapped[UUID] = mapped_column(ForeignKey("scan_runs.id", ondelete="CASCADE"))
    schema_name: Mapped[str] = mapped_column(String(63))
    table_name: Mapped[str] = mapped_column(String(63))
    name: Mapped[str] = mapped_column(String(63))
    data_type_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    nullable: Mapped[bool]
    default_expression: Mapped[str | None] = mapped_column("default", String(1000))
    ordinal: Mapped[int] = mapped_column(Integer)

    scan: Mapped[ScanRunModel] = relationship(back_populates="observed_columns")


class SchemaChangeModel(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "schema_changes"
    __table_args__ = (
        Index(
            "uq_schema_changes_open_fingerprint",
            "source_id",
            "fingerprint",
            unique=True,
            postgresql_where=text("state = 'OPEN'"),
        ),
    )

    scan_id: Mapped[UUID] = mapped_column(ForeignKey("scan_runs.id", ondelete="CASCADE"))
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"))
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    column_name: Mapped[str] = mapped_column(String(63))
    change_type: Mapped[ChangeType] = mapped_column(
        Enum(ChangeType, native_enum=False, create_constraint=True, name="change_type")
    )
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, native_enum=False, create_constraint=True, name="severity")
    )
    state: Mapped[ChangeState] = mapped_column(
        Enum(ChangeState, native_enum=False, create_constraint=True, name="change_state"),
        default=ChangeState.OPEN,
        server_default=ChangeState.OPEN.value,
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    baseline_version: Mapped[int] = mapped_column(Integer)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scan: Mapped[ScanRunModel] = relationship()
    source: Mapped[DataSourceModel] = relationship()
    dataset: Mapped[DatasetModel] = relationship()
