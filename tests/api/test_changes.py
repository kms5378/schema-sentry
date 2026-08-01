from uuid import uuid4

from fastapi.testclient import TestClient

from schema_sentry.application.change_service import BaselineVersionConflict, ChangeNotFound
from tests.api.conftest import ApiFakes


def test_accept_change_returns_new_baseline_version(
    client: TestClient, api_headers: dict[str, str]
) -> None:
    change_id = uuid4()

    response = client.post(
        f"/api/v1/changes/{change_id}/accept",
        json={"baseline_version": 7},
        headers=api_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"change_id": str(change_id), "baseline_version": 8}


def test_stale_acceptance_returns_conflict(
    client: TestClient, api_headers: dict[str, str], api_fakes: ApiFakes
) -> None:
    api_fakes.change.error = BaselineVersionConflict(expected=6, actual=7)

    response = client.post(
        f"/api/v1/changes/{uuid4()}/accept",
        json={"baseline_version": 6},
        headers=api_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"expected": 6, "actual": 7}


def test_missing_change_returns_404(
    client: TestClient, api_headers: dict[str, str], api_fakes: ApiFakes
) -> None:
    change_id = uuid4()
    api_fakes.change.error = ChangeNotFound(change_id)

    response = client.post(
        f"/api/v1/changes/{change_id}/accept",
        json={"baseline_version": 1},
        headers=api_headers,
    )

    assert response.status_code == 404
