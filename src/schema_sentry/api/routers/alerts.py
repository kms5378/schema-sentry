from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from schema_sentry.api.dependencies import get_notification_service
from schema_sentry.api.schemas.alerts import DeliveryResultResponse
from schema_sentry.api.security import OperatorIdentity, require_operator
from schema_sentry.application.notification_service import (
    DeliveryNotFound,
    MaxAttemptsExceeded,
    NotificationService,
    RetryNotDue,
)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.post("/{delivery_id}/retry", response_model=DeliveryResultResponse)
def retry_delivery(
    delivery_id: UUID,
    _: Annotated[OperatorIdentity, Depends(require_operator)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> DeliveryResultResponse:
    try:
        return DeliveryResultResponse.from_result(service.retry(delivery_id))
    except DeliveryNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MaxAttemptsExceeded as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RetryNotDue as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"next_retry_at": exc.next_retry_at.isoformat().replace("+00:00", "Z")},
        ) from exc
