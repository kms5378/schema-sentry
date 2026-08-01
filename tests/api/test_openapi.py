from fastapi.testclient import TestClient

from tests.api.conftest import API_KEY


def test_openapi_contains_approved_routes_and_security_without_secrets(
    client: TestClient,
) -> None:
    document = client.app.openapi()

    assert set(document["paths"]) >= {
        "/api/v1/scans",
        "/api/v1/scans/latest",
        "/api/v1/scans/{scan_id}",
        "/api/v1/changes/{change_id}/accept",
        "/api/v1/pipelines/{pipeline_key}/validate",
        "/health/live",
        "/health/ready",
    }
    assert document["paths"]["/api/v1/scans"]["post"]["security"] == [
        {"APIKeyHeader": []}
    ]
    assert API_KEY not in str(document)
