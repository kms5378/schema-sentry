from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from schema_sentry.api.dependencies import (
    NotificationDispatcher,
    get_change_service,
    get_database_session,
    get_notification_dispatcher,
    get_scan_query_service,
    get_scan_service,
)
from schema_sentry.api.security import OperatorIdentity, require_operator
from schema_sentry.application.change_service import (
    BaselineVersionConflict,
    ChangeNotFound,
    ChangeService,
)
from schema_sentry.application.query_service import ScanQueryService
from schema_sentry.application.scan_service import (
    EmptySchemaSnapshot,
    ScanAlreadyRunning,
    ScanService,
)
from schema_sentry.config import Settings, get_settings
from schema_sentry.domain.enums import ScanTrigger
from schema_sentry.infrastructure.db.repositories.scans import SourceNotFound

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def _column_type(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "Not present"
    data_type = snapshot.get("data_type", {})
    name = str(data_type.get("name", "unknown"))
    length = data_type.get("length")
    precision = data_type.get("precision")
    scale = data_type.get("scale")
    if length is not None:
        return f"{name}({length})"
    if precision is not None and scale is not None:
        return f"{name}({precision},{scale})"
    if precision is not None:
        return f"{name}({precision})"
    return name


def _timestamp(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if value else "—"


templates.env.filters["column_type"] = _column_type
templates.env.filters["timestamp"] = _timestamp


def _require_same_origin(
    request: Request,
    identity: OperatorIdentity,
    settings: Settings,
) -> None:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    supplied_url = origin or referer
    if supplied_url:
        supplied = urlsplit(supplied_url)
        expected = urlsplit(str(settings.dashboard_base_url))
        if (supplied.scheme, supplied.netloc) == (expected.scheme, expected.netloc):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross-origin request")
    if identity.mechanism == "api-key":
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="same-origin browser request required",
    )


def _render_change_list(
    request: Request,
    query_service: ScanQueryService,
    *,
    message: str | None = None,
    message_kind: str = "success",
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="partials/change_list.html",
        context={
            "scan": query_service.latest(),
            "message": message,
            "message_kind": message_kind,
        },
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    query_service: Annotated[ScanQueryService, Depends(get_scan_query_service)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "scan": query_service.latest(),
            "recent_scans": query_service.recent(5),
        },
    )


@router.post("/actions/scans", response_class=HTMLResponse)
def run_scan(
    request: Request,
    background_tasks: BackgroundTasks,
    identity: Annotated[OperatorIdentity, Depends(require_operator)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[ScanService, Depends(get_scan_service)],
    query_service: Annotated[ScanQueryService, Depends(get_scan_query_service)],
    dispatcher: Annotated[NotificationDispatcher, Depends(get_notification_dispatcher)],
    session: Annotated[Session, Depends(get_database_session)],
    source_key: Annotated[str, Form(min_length=1, max_length=100)] = "game",
) -> HTMLResponse:
    _require_same_origin(request, identity, settings)
    try:
        report = service.run_scan(source_key, ScanTrigger.MANUAL)
        session.commit()
        background_tasks.add_task(dispatcher.dispatch_scan, report.scan_id)
        return _render_change_list(
            request,
            query_service,
            message=f"Scan {report.scan_id} completed.",
        )
    except ScanAlreadyRunning:
        return _render_change_list(
            request,
            query_service,
            message="A scan is already running. Try again shortly.",
            message_kind="warning",
            status_code=status.HTTP_409_CONFLICT,
        )
    except SourceNotFound:
        return _render_change_list(
            request,
            query_service,
            message=f"Source '{source_key}' is not registered.",
            message_kind="error",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except (psycopg.Error, OSError, EmptySchemaSnapshot):
        session.commit()
        dispatcher.dispatch_system_error(source_key)
        return _render_change_list(
            request,
            query_service,
            message="Source database is unavailable. The failure was recorded.",
            message_kind="error",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@router.post("/actions/changes/{change_id}/accept", response_class=HTMLResponse)
def accept_change(
    request: Request,
    change_id: UUID,
    baseline_version: Annotated[int, Form(ge=0)],
    identity: Annotated[OperatorIdentity, Depends(require_operator)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[ChangeService, Depends(get_change_service)],
    query_service: Annotated[ScanQueryService, Depends(get_scan_query_service)],
) -> HTMLResponse:
    _require_same_origin(request, identity, settings)
    try:
        result = service.accept(change_id, baseline_version)
    except BaselineVersionConflict as exc:
        return _render_change_list(
            request,
            query_service,
            message=(
                f"Baseline changed to version {exc.actual}. Refresh the page before accepting."
            ),
            message_kind="warning",
            status_code=status.HTTP_409_CONFLICT,
        )
    except ChangeNotFound:
        return _render_change_list(
            request,
            query_service,
            message="This schema change no longer exists. Refresh the page.",
            message_kind="error",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _render_change_list(
        request,
        query_service,
        message=f"Accepted as baseline version {result.baseline_version}.",
    )
