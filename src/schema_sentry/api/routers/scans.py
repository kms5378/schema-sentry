from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from schema_sentry.api.dependencies import (
    NotificationDispatcher,
    get_database_session,
    get_notification_dispatcher,
    get_scan_query_service,
    get_scan_service,
)
from schema_sentry.api.schemas.scans import ManualScanRequest, ScanDetailResponse, ScanResponse
from schema_sentry.api.security import OperatorIdentity, require_operator
from schema_sentry.application.query_service import ScanQueryService
from schema_sentry.application.scan_service import (
    EmptySchemaSnapshot,
    ScanAlreadyRunning,
    ScanService,
)
from schema_sentry.domain.enums import ScanTrigger
from schema_sentry.infrastructure.db.repositories.scans import SourceNotFound

router = APIRouter(prefix="/api/v1/scans", tags=["scans"])


@router.post("", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
def run_scan(
    request: ManualScanRequest,
    background_tasks: BackgroundTasks,
    _: Annotated[OperatorIdentity, Depends(require_operator)],
    service: Annotated[ScanService, Depends(get_scan_service)],
    dispatcher: Annotated[NotificationDispatcher, Depends(get_notification_dispatcher)],
    session: Annotated[Session, Depends(get_database_session)],
) -> ScanResponse:
    try:
        report = service.run_scan(request.source_key, ScanTrigger.MANUAL)
        session.commit()
        background_tasks.add_task(dispatcher.dispatch_scan, report.scan_id)
        return ScanResponse.from_report(report)
    except ScanAlreadyRunning as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SourceNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (psycopg.Error, OSError, EmptySchemaSnapshot) as exc:
        session.commit()
        dispatcher.dispatch_system_error(request.source_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="source database unavailable",
        ) from exc


@router.get("/latest", response_model=ScanDetailResponse)
def latest_scan(
    service: Annotated[ScanQueryService, Depends(get_scan_query_service)],
) -> ScanDetailResponse:
    scan = service.latest()
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    return ScanDetailResponse.from_persisted(scan)


@router.get("/{scan_id}", response_model=ScanDetailResponse)
def get_scan(
    scan_id: UUID,
    service: Annotated[ScanQueryService, Depends(get_scan_query_service)],
) -> ScanDetailResponse:
    scan = service.get(scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    return ScanDetailResponse.from_persisted(scan)
