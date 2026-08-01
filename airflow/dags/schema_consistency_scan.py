from datetime import timedelta

from airflow.sdk import dag, task
from airflow.sdk.exceptions import AirflowException
from schema_sentry_client import post_json


def run_schema_scan() -> None:
    response = post_json("/api/v1/scans", {"source_key": "game"})
    if response.status != 201:
        raise AirflowException(f"Schema Sentry scan failed with HTTP {response.status}")


@dag(
    dag_id="schema_consistency_scan",
    schedule="*/10 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    tags=["schema-sentry", "metadata"],
)
def schema_scan_dag() -> None:
    @task(task_id="trigger_scan", retries=2, retry_delay=timedelta(minutes=1))
    def trigger_scan() -> None:
        run_schema_scan()

    trigger_scan()


schema_scan_dag()
