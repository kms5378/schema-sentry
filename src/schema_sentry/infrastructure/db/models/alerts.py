from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schema_sentry.domain.enums import AlertChannel, AlertStatus
from schema_sentry.infrastructure.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from schema_sentry.infrastructure.db.models.scans import ScanRunModel


class AlertDeliveryModel(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "alert_deliveries"

    scan_id: Mapped[UUID] = mapped_column(ForeignKey("scan_runs.id", ondelete="CASCADE"))
    channel: Mapped[AlertChannel] = mapped_column(
        Enum(AlertChannel, native_enum=False, create_constraint=True, name="alert_channel")
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, native_enum=False, create_constraint=True, name="alert_status"),
        default=AlertStatus.PENDING,
        server_default=AlertStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    provider_message_id: Mapped[str | None] = mapped_column(String(250))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scan: Mapped[ScanRunModel] = relationship()
