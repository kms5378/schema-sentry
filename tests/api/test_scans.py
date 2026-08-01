from uuid import uuid4

from fastapi.testclient import TestClient

from schema_sentry.application.scan_service import ScanAlreadyRunning
from tests.api.conftest import SCAN_ID, ApiFakes


def test_manual_scan_requires_operator_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/scans", json={"source_key": "game"})

    assert response.status_code == 401


def test_manual_scan_returns_created_report(
    client: TestClient, api_headers: dict[str, str]
) -> None:
    response = client.post("/api/v1/scans", json={"source_key": "game"}, headers=api_headers)

    assert response.status_code == 201
    assert response.json() == {
        "scan_id": str(SCAN_ID),
        "source_key": "game",
        "trigger": "MANUAL",
        "baseline_created": False,
        "observed_count": 16,
        "changes": [],
    }


def test_concurrent_scan_returns_conflict(
    client: TestClient, api_headers: dict[str, str], api_fakes: ApiFakes
) -> None:
    api_fakes.scan.error = ScanAlreadyRunning("game")

    response = client.post("/api/v1/scans", json={"source_key": "game"}, headers=api_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "scan already running for source: game"


def test_source_failure_is_sanitized(
    client: TestClient, api_headers: dict[str, str], api_fakes: ApiFakes
) -> None:
    api_fakes.scan.error = ConnectionError("password=never-return-this")

    response = client.post("/api/v1/scans", json={"source_key": "game"}, headers=api_headers)

    assert response.status_code == 503
    assert response.json() == {"detail": "source database unavailable"}


def test_scan_request_validation_returns_422(
    client: TestClient, api_headers: dict[str, str]
) -> None:
    assert client.post("/api/v1/scans", json={}, headers=api_headers).status_code == 422


def test_latest_and_individual_scan_are_publicly_readable(client: TestClient) -> None:
    latest = client.get("/api/v1/scans/latest")
    individual = client.get(f"/api/v1/scans/{SCAN_ID}")

    assert latest.status_code == individual.status_code == 200
    assert latest.json()["status"] == "COMPLETED"
    assert individual.json()["scan_id"] == str(SCAN_ID)


def test_missing_scan_returns_404(client: TestClient) -> None:
    assert client.get(f"/api/v1/scans/{uuid4()}").status_code == 404
