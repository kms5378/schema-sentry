from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from schema_sentry.api.dependencies import ReadinessChecker, get_readiness_checker

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def readiness(
    checker: Annotated[ReadinessChecker, Depends(get_readiness_checker)],
) -> JSONResponse:
    ready = checker.check()
    return JSONResponse(
        {"status": "ready" if ready else "not-ready"},
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
