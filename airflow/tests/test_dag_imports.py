from airflow.models import DagBag


def test_schema_scan_schedule(dag_bag: DagBag) -> None:
    dag = dag_bag.get_dag("schema_consistency_scan")

    assert dag_bag.import_errors == {}
    assert dag is not None
    assert str(dag.schedule) == "*/10 * * * *"
    assert dag.is_paused_upon_creation is False
    assert set(dag.task_dict) == {"trigger_scan"}


def test_daily_revenue_guard_precedes_sql(dag_bag: DagBag) -> None:
    dag = dag_bag.get_dag("daily_revenue")

    assert dag_bag.import_errors == {}
    assert dag is not None
    assert dag.is_paused_upon_creation is False
    assert dag.task_dict["schema_guard"].downstream_task_ids == {
        "aggregate_daily_revenue"
    }
