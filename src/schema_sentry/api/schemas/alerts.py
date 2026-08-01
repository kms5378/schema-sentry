from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from schema_sentry.application.notification_service import DeliveryResult
from schema_sentry.domain.enums import AlertChannel


class DeliveryResultResponse(BaseModel):
    delivery_id: UUID
    channel: AlertChannel
    success: bool
    attempt_count: int
    next_retry_at: datetime | None

    @classmethod
    def from_result(cls, result: DeliveryResult) -> "DeliveryResultResponse":
        return cls(
            delivery_id=result.delivery_id,
            channel=result.channel,
            success=result.success,
            attempt_count=result.attempt_count,
            next_retry_at=result.next_retry_at,
        )
