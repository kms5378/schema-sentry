from schema_sentry.domain.enums import ChangeType, PipelineCriticality, Severity
from schema_sentry.domain.lineage import LineageEdge, LineageGraph, PipelineDefinition
from schema_sentry.domain.models import (
    CanonicalType,
    ColumnDefinition,
    ColumnRef,
    DatasetRef,
    SchemaChange,
)


def column(schema: str, table: str, name: str) -> ColumnRef:
    return ColumnRef(DatasetRef(schema, table), name)


def breaking_amount_change() -> SchemaChange:
    before = ColumnDefinition(
        dataset=DatasetRef("public", "purchases"),
        name="amount",
        data_type=CanonicalType("numeric", precision=12, scale=2),
        nullable=False,
        default=None,
    )
    after = ColumnDefinition(
        dataset=before.dataset,
        name="amount",
        data_type=CanonicalType("character varying"),
        nullable=False,
        default=None,
    )
    return SchemaChange(
        dataset=before.dataset,
        column_name="amount",
        change_type=ChangeType.TYPE_CHANGE,
        severity=Severity.BREAKING,
        before=before,
        after=after,
    )


def test_impact_traverses_multiple_downstream_pipelines() -> None:
    daily = PipelineDefinition(
        key="daily_revenue",
        airflow_dag_id="daily_revenue_dag",
        owner="analytics",
        criticality=PipelineCriticality.CRITICAL,
    )
    executive = PipelineDefinition(
        key="executive_kpi",
        airflow_dag_id="executive_kpi_dag",
        owner="analytics",
        criticality=PipelineCriticality.HIGH,
    )
    graph = LineageGraph(
        (
            LineageEdge(
                daily,
                column("public", "purchases", "amount"),
                column("mart", "daily_revenue", "revenue"),
            ),
            LineageEdge(
                executive,
                column("mart", "daily_revenue", "revenue"),
                column("mart", "executive_kpi", "total_revenue"),
            ),
        )
    )

    impacts = graph.impacts((breaking_amount_change(),))

    assert [
        (impact.pipeline.key, impact.downstream.dataset.qualified_name) for impact in impacts
    ] == [
        ("daily_revenue", "mart.daily_revenue"),
        ("executive_kpi", "mart.executive_kpi"),
    ]
    assert len(impacts[1].path) == 2


def test_non_breaking_change_does_not_report_pipeline_impact() -> None:
    change = breaking_amount_change()
    warning = SchemaChange(
        dataset=change.dataset,
        column_name=change.column_name,
        change_type=change.change_type,
        severity=Severity.WARNING,
        before=change.before,
        after=change.after,
    )

    assert LineageGraph(()).impacts((warning,)) == ()
