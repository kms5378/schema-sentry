from fastapi import FastAPI

from schema_sentry.api.routers import alerts, changes, health, pipelines, scans


def create_app() -> FastAPI:
    app = FastAPI(title="Schema Sentry", version="0.1.0")
    app.include_router(health.router)
    app.include_router(scans.router)
    app.include_router(changes.router)
    app.include_router(pipelines.router)
    app.include_router(alerts.router)
    return app
