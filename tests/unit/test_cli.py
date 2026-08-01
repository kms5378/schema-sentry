from typer.testing import CliRunner

from schema_sentry.application.catalog_service import CatalogSyncResult
from schema_sentry.cli import app


def test_catalog_sync_command_reports_counts(monkeypatch) -> None:
    monkeypatch.setattr(
        "schema_sentry.cli._sync_catalog",
        lambda path: CatalogSyncResult(pipeline_count=2, edge_count=7),
    )

    result = CliRunner().invoke(app, ["catalog", "sync", "catalog.yaml"])

    assert result.exit_code == 0
    assert result.stdout == "synced pipelines=2 edges=7\n"
