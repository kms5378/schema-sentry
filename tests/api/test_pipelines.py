from uuid import uuid4

from fastapi.testclient import TestClient

from schema_sentry.application.validation_service import BlockingChange, PipelineValidation
from schema_sentry.domain.enums import ChangeType, Severity
from schema_sentry.domain.models import DatasetRef
from tests.api.conftest import ApiFakes


def test_pipeline_conflict_shape(
    client: TestClient, api_headers: dict[str, str], api_fakes: ApiFakes
) -> None:
    api_fakes.validation.result = PipelineValidation(
        pipeline_key="daily_revenue",
        safe=False,
        blocking_changes=(
            BlockingChange(
                id=uuid4(),
                dataset=DatasetRef("public", "purchases"),
                column_name="amount",
                change_type=ChangeType.TYPE_CHANGE,
                severity=Severity.BREAKING,
            ),
        ),
    )

    response = client.post("/api/v1/pipelines/daily_revenue/validate", headers=api_headers)

    assert response.status_code == 409
    assert response.json()["safe"] is False
    assert response.json()["blocking_changes"][0]["severity"] == "BREAKING"


def test_safe_pipeline_returns_200(client: TestClient, api_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/pipelines/daily_revenue/validate", headers=api_headers)

    assert response.status_code == 200
    assert response.json() == {
        "pipeline_key": "daily_revenue",
        "safe": True,
        "blocking_changes": [],
    }


def test_pipeline_validation_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/v1/pipelines/daily_revenue/validate").status_code == 401
