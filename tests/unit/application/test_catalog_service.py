from pathlib import Path

import pytest

from schema_sentry.application.catalog_service import CatalogService, CatalogValidationError
from schema_sentry.domain.models import ColumnRef, DatasetRef


class FakeCatalogRepository:
    def __init__(self) -> None:
        self.columns = {
            ColumnRef(DatasetRef("public", "purchases"), "amount"),
            ColumnRef(DatasetRef("mart", "daily_revenue"), "revenue"),
        }
        self.replacements: list[tuple[object, object]] = []

    def known_columns(self) -> set[ColumnRef]:
        return self.columns

    def replace_catalog(self, pipelines: object, edges: object) -> None:
        self.replacements.append((pipelines, edges))


def write_catalog(path: Path, *, input_column: str = "amount") -> Path:
    path.write_text(
        f"""
pipelines:
  - key: daily_revenue
    airflow_dag_id: daily_revenue_dag
    owner: analytics
    criticality: critical
    inputs:
      - dataset: public.purchases
        columns: [{input_column}]
    outputs:
      - dataset: mart.daily_revenue
        columns: [revenue]
""".lstrip()
    )
    return path


def test_valid_catalog_builds_pipeline_and_edges(tmp_path: Path) -> None:
    repository = FakeCatalogRepository()

    result = CatalogService(repository).sync(write_catalog(tmp_path / "catalog.yaml"))

    assert result.pipeline_count == 1
    assert result.edge_count == 1
    assert len(repository.replacements) == 1


def test_unknown_column_is_rejected_before_repository_replacement(tmp_path: Path) -> None:
    repository = FakeCatalogRepository()

    with pytest.raises(CatalogValidationError, match="unknown column"):
        CatalogService(repository).sync(
            write_catalog(tmp_path / "invalid.yaml", input_column="missing")
        )

    assert repository.replacements == []


def test_duplicate_pipeline_key_is_rejected(tmp_path: Path) -> None:
    repository = FakeCatalogRepository()
    valid = write_catalog(tmp_path / "catalog.yaml").read_text()
    duplicate = valid + valid.removeprefix("pipelines:\n")
    path = tmp_path / "duplicate.yaml"
    path.write_text(duplicate)

    with pytest.raises(CatalogValidationError, match="duplicate pipeline key"):
        CatalogService(repository).sync(path)
