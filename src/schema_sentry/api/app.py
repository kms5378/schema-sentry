from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from schema_sentry.api.routers import alerts, changes, dashboard, health, pipelines, scans
from schema_sentry.config import get_settings
from schema_sentry.logging import configure_logging

STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    app = FastAPI(title="Schema Sentry", version="0.1.0")

    @app.middleware("http")
    async def add_browser_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
    app.include_router(dashboard.router)
    app.include_router(health.router)
    app.include_router(scans.router)
    app.include_router(changes.router)
    app.include_router(pipelines.router)
    app.include_router(alerts.router)
    return app
