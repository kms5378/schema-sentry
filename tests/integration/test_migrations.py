from alembic.config import Config
from sqlalchemy import Engine, inspect

from alembic import command

APPLICATION_TABLES = {
    "alert_deliveries",
    "data_sources",
    "datasets",
    "expected_columns",
    "lineage_edges",
    "observed_columns",
    "pipelines",
    "scan_runs",
    "schema_changes",
}


def test_upgrade_creates_all_repository_tables(
    metadata_engine: Engine,
    alembic_config: Config,
    empty_repository: None,
) -> None:
    command.upgrade(alembic_config, "head")

    assert set(inspect(metadata_engine).get_table_names()) == APPLICATION_TABLES | {
        "alembic_version"
    }


def test_downgrade_removes_all_application_tables(
    metadata_engine: Engine,
    alembic_config: Config,
    empty_repository: None,
) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    assert not (set(inspect(metadata_engine).get_table_names()) & APPLICATION_TABLES)
