FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 schema-sentry
USER schema-sentry

EXPOSE 8000

CMD [".venv/bin/uvicorn", "schema_sentry.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
