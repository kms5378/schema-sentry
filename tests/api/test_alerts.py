from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from schema_sentry.application.notification_service import (
    DeliveryNotFound,
    MaxAttemptsExceeded,
    RetryNotDue,
)
from tests.api.conftest import ApiFakes


def test_retry_delivery_returns_attempt_result(
    client: TestClient, api_headers: dict[str, str]
) -> None:
    delivery_id = uuid4()

    response = client.post(f"/api/v1/alerts/{delivery_id}/retry", headers=api_headers)

    assert response.status_code == 200
    assert response.json() == {
        "delivery_id": str(delivery_id),
        "channel": "SLACK",
        "success": True,
        "attempt_count": 2,
        "next_retry_at": None,
    }


def test_retry_requires_authentication(client: TestClient) -> None:
    assert client.post(f"/api/v1/alerts/{uuid4()}/retry").status_code == 401


def test_retry_limit_returns_conflict(
    client: TestClient, api_headers: dict[str, str], api_fakes: ApiFakes
) -> None:
    delivery_id = uuid4()
    api_fakes.notification.error = MaxAttemptsExceeded(delivery_id)

    response = client.post(f"/api/v1/alerts/{delivery_id}/retry", headers=api_headers)

    assert response.status_code == 409


def test_retry_not_due_returns_conflict_with_timestamp(
    client: TestClient, api_headers: dict[str, str], api_fakes: ApiFakes
) -> None:
    due_at = datetime(2026, 8, 1, 0, 1, tzinfo=UTC)
    api_fakes.notification.error = RetryNotDue(due_at)

    response = client.post(f"/api/v1/alerts/{uuid4()}/retry", headers=api_headers)

    assert response.status_code == 409
    assert response.json()["detail"]["next_retry_at"] == "2026-08-01T00:01:00Z"


def test_missing_delivery_returns_404(
    client: TestClient, api_headers: dict[str, str], api_fakes: ApiFakes
) -> None:
    delivery_id = uuid4()
    api_fakes.notification.error = DeliveryNotFound(delivery_id)

    response = client.post(f"/api/v1/alerts/{delivery_id}/retry", headers=api_headers)

    assert response.status_code == 404
