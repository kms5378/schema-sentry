from pathlib import Path

import typer

from schema_sentry.application.catalog_service import CatalogService, CatalogSyncResult
from schema_sentry.config import get_settings
from schema_sentry.infrastructure.db.repositories.catalog import CatalogRepository
from schema_sentry.infrastructure.db.session import create_session_factory, session_scope

app = typer.Typer(no_args_is_help=True)
catalog_app = typer.Typer(no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")


def _sync_catalog(path: Path) -> CatalogSyncResult:
    settings = get_settings()
    factory = create_session_factory(settings.metadata_database_url)
    with session_scope(factory) as session:
        return CatalogService(CatalogRepository(session)).sync(path)


@catalog_app.command("sync")
def sync_catalog(path: Path) -> None:
    result = _sync_catalog(path)
    typer.echo(f"synced pipelines={result.pipeline_count} edges={result.edge_count}")
