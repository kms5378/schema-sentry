from typing import Final

from fastapi import FastAPI

APP_TITLE: Final = "Schema Sentry"


def liveness() -> dict[str, str]:
    return {"status": "alive"}


def create_app() -> FastAPI:
    app = FastAPI(title=APP_TITLE, version="0.1.0")
    app.add_api_route("/health/live", liveness, methods=["GET"], tags=["health"])
    return app
