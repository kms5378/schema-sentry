import sys
from pathlib import Path

import pytest
from airflow.models import DagBag

DAG_FOLDER = Path(__file__).parents[1] / "dags"
sys.path.insert(0, str(DAG_FOLDER))


@pytest.fixture(scope="session")
def dag_bag() -> DagBag:
    return DagBag(dag_folder=str(DAG_FOLDER))
