from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schema_sentry.domain.enums import PipelineCriticality
from schema_sentry.infrastructure.db.base import Base, UUIDPrimaryKeyMixin
from schema_sentry.infrastructure.db.models.catalog import DatasetModel


class PipelineModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pipelines"

    key: Mapped[str] = mapped_column(String(100), unique=True)
    airflow_dag_id: Mapped[str] = mapped_column(String(250), unique=True)
    owner: Mapped[str] = mapped_column(String(200))
    criticality: Mapped[PipelineCriticality] = mapped_column(
        Enum(
            PipelineCriticality,
            native_enum=False,
            create_constraint=True,
            name="pipeline_criticality",
        )
    )


class LineageEdgeModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "lineage_edges"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_id",
            "upstream_dataset_id",
            "upstream_column",
            "downstream_dataset_id",
            "downstream_column",
            name="lineage_edge_identity",
        ),
    )

    pipeline_id: Mapped[UUID] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"))
    upstream_dataset_id: Mapped[UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    upstream_column: Mapped[str] = mapped_column(String(63))
    downstream_dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE")
    )
    downstream_column: Mapped[str] = mapped_column(String(63))

    pipeline: Mapped[PipelineModel] = relationship()
    upstream_dataset: Mapped[DatasetModel] = relationship(foreign_keys=[upstream_dataset_id])
    downstream_dataset: Mapped[DatasetModel] = relationship(foreign_keys=[downstream_dataset_id])
