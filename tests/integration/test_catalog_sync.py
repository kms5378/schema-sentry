from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from schema_sentry.application.catalog_service import CatalogService, CatalogValidationError
from schema_sentry.infrastructure.db.models import (
    DatasetModel,
    DataSourceModel,
    ExpectedColumnModel,
    LineageEdgeModel,
    PipelineModel,
)
from schema_sentry.infrastructure.db.repositories.catalog import CatalogRepository


def seed_catalog_columns(session: Session) -> None:
    source = DataSourceModel(
        key="game",
        display_name="Game database",
        connection_ref="SCHEMA_SENTRY_SOURCE_DATABASE_URL",
    )
    purchases = DatasetModel(source=source, schema_name="public", table_name="purchases")
    daily = DatasetModel(source=source, schema_name="mart", table_name="daily_revenue")
    session.add_all(
        [
            ExpectedColumnModel(
                dataset=purchases,
                name="purchased_at",
                data_type_json={"name": "timestamp with time zone"},
                nullable=False,
                ordinal=3,
            ),
            ExpectedColumnModel(
                dataset=purchases,
                name="amount",
                data_type_json={"name": "numeric", "precision": 12, "scale": 2},
                nullable=False,
                ordinal=4,
            ),
            ExpectedColumnModel(
                dataset=daily,
                name="date",
                data_type_json={"name": "date"},
                nullable=False,
                ordinal=1,
            ),
            ExpectedColumnModel(
                dataset=daily,
                name="revenue",
                data_type_json={"name": "numeric", "precision": 18, "scale": 2},
                nullable=False,
                ordinal=2,
            ),
        ]
    )
    session.flush()


def test_catalog_sync_is_atomic_and_idempotent(session: Session, tmp_path: Path) -> None:
    seed_catalog_columns(session)
    repository = CatalogRepository(session)
    service = CatalogService(repository)

    first = service.sync(Path("catalog.yaml"))
    first_digest = repository.catalog_digest()
    second = service.sync(Path("catalog.yaml"))

    assert first.pipeline_count == second.pipeline_count == 1
    assert first.edge_count == second.edge_count == 4
    assert repository.catalog_digest() == first_digest
    assert session.scalar(select(func.count()).select_from(PipelineModel)) == 1
    assert session.scalar(select(func.count()).select_from(LineageEdgeModel)) == 4

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(Path("catalog.yaml").read_text().replace("amount]", "missing]"))
    with pytest.raises(CatalogValidationError, match="unknown column"):
        service.sync(invalid)

    assert repository.catalog_digest() == first_digest
