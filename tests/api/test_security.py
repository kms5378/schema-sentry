from fastapi.testclient import TestClient
from pydantic import SecretStr

from schema_sentry.config import Settings, get_settings


def test_trusted_proxy_identity_is_accepted(client: TestClient) -> None:
    settings = Settings(
        environment="test",
        metadata_database_url="postgresql+psycopg://unused",
        source_database_url="postgresql+psycopg://unused",
        api_key=SecretStr("different-key"),
        trust_proxy_auth=True,
    )
    client.app.dependency_overrides[get_settings] = lambda: settings

    response = client.post(
        "/api/v1/scans",
        json={"source_key": "game"},
        headers={"X-Authenticated-User": "portfolio-reviewer"},
    )

    assert response.status_code == 201


def test_untrusted_proxy_header_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/scans",
        json={"source_key": "game"},
        headers={"X-Authenticated-User": "spoofed-user"},
    )

    assert response.status_code == 401
