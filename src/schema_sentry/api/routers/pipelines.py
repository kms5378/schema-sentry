from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from schema_sentry.api.dependencies import get_validation_service
from schema_sentry.api.schemas.pipelines import PipelineValidationResponse
from schema_sentry.api.security import OperatorIdentity, require_operator
from schema_sentry.application.validation_service import ValidationService

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])


@router.post("/{pipeline_key}/validate", response_model=PipelineValidationResponse)
def validate_pipeline(
    pipeline_key: str,
    _: Annotated[OperatorIdentity, Depends(require_operator)],
    service: Annotated[ValidationService, Depends(get_validation_service)],
) -> JSONResponse:
    try:
        result = service.validate_pipeline(pipeline_key)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    body = PipelineValidationResponse.from_domain(result).model_dump(mode="json")
    return JSONResponse(
        body,
        status_code=status.HTTP_200_OK if result.safe else status.HTTP_409_CONFLICT,
    )
