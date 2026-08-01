from fastapi.testclient import TestClient

from tests.api.conftest import ApiFakes


def test_liveness_does_not_require_dependencies(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "alive"}


def test_readiness_reports_repository_and_migration_state(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_unready_repository_returns_503(client: TestClient, api_fakes: ApiFakes) -> None:
    api_fakes.readiness.ready = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not-ready"}
