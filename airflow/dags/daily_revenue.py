import os
from datetime import timedelta

import psycopg
from airflow.sdk import dag, task
from airflow.sdk.exceptions import AirflowException, AirflowFailException
from schema_sentry_client import JsonResponse, post_json

AGGREGATE_DAILY_REVENUE_SQL = """
INSERT INTO mart.daily_revenue (date, revenue)
SELECT purchased_at::date, SUM(amount)
FROM public.purchases
GROUP BY purchased_at::date
ON CONFLICT (date) DO UPDATE SET revenue = EXCLUDED.revenue
"""


def validate_pipeline(pipeline_key: str) -> None:
    response: JsonResponse = post_json(
        f"/api/v1/pipelines/{pipeline_key}/validate",
        {},
    )
    if response.status == 200 and response.body.get("safe") is True:
        return
    if response.status in {200, 409}:
        raise AirflowFailException(f"blocking schema drift detected for {pipeline_key}")
    raise AirflowException(f"Schema Sentry validation failed with HTTP {response.status}")


def aggregate_daily_revenue() -> None:
    source_database_url = os.environ["SOURCE_DATABASE_URL"]
    with psycopg.connect(
        source_database_url,
        connect_timeout=5,
        options="-c statement_timeout=30000",
    ) as connection:
        connection.execute(AGGREGATE_DAILY_REVENUE_SQL)


@dag(
    dag_id="daily_revenue",
    schedule="0 1 * * *",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["analytics", "schema-sentry"],
)
def daily_revenue_dag() -> None:
    @task(task_id="schema_guard", retries=2, retry_delay=timedelta(minutes=1))
    def schema_guard_task() -> None:
        validate_pipeline("daily_revenue")

    @task(task_id="aggregate_daily_revenue", execution_timeout=timedelta(minutes=2))
    def aggregate_daily_revenue_task() -> None:
        aggregate_daily_revenue()

    schema_guard_task() >> aggregate_daily_revenue_task()


daily_revenue_dag()
