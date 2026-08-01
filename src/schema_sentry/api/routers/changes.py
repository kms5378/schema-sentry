from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from schema_sentry.api.dependencies import get_change_service
from schema_sentry.api.schemas.changes import AcceptanceResponse, AcceptChangeRequest
from schema_sentry.api.security import OperatorIdentity, require_operator
from schema_sentry.application.change_service import (
    BaselineVersionConflict,
    ChangeNotFound,
    ChangeService,
)

router = APIRouter(prefix="/api/v1/changes", tags=["changes"])


@router.post("/{change_id}/accept", response_model=AcceptanceResponse)
def accept_change(
    change_id: UUID,
    request: AcceptChangeRequest,
    _: Annotated[OperatorIdentity, Depends(require_operator)],
    service: Annotated[ChangeService, Depends(get_change_service)],
) -> AcceptanceResponse:
    try:
        result = service.accept(change_id, request.baseline_version)
    except BaselineVersionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"expected": exc.expected, "actual": exc.actual},
        ) from exc
    except ChangeNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AcceptanceResponse.from_result(result)
