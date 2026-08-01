from io import BytesIO
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from airflow.sdk.exceptions import AirflowFailException


class StubResponse:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self.body = body


class UrlResponse:
    status = 201

    def __enter__(self) -> "UrlResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @staticmethod
    def read() -> bytes:
        return b'{"scan_id":"scan-1"}'


def test_client_sends_api_key_with_five_second_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import schema_sentry_client

    captured: dict[str, Any] = {}

    def fake_urlopen(request: Request, timeout: int) -> UrlResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return UrlResponse()

    monkeypatch.setenv("SCHEMA_SENTRY_API_URL", "http://schema-sentry:8000/")
    monkeypatch.setenv("SCHEMA_SENTRY_API_KEY", "airflow-secret")
    monkeypatch.setattr(schema_sentry_client, "urlopen", fake_urlopen)

    response = schema_sentry_client.post_json("/api/v1/scans", {"source_key": "game"})

    request = captured["request"]
    assert isinstance(request, Request)
    assert request.full_url == "http://schema-sentry:8000/api/v1/scans"
    assert request.get_header("X-api-key") == "airflow-secret"
    assert captured["timeout"] == 5
    assert response.status == 201


def test_client_decodes_http_409_response(monkeypatch: pytest.MonkeyPatch) -> None:
    import schema_sentry_client

    def blocking_urlopen(_request: Request, timeout: int) -> UrlResponse:
        assert timeout == 5
        raise HTTPError(
            "http://schema-sentry:8000/api/v1/pipelines/daily_revenue/validate",
            409,
            "Conflict",
            {},
            BytesIO(b'{"safe":false}'),
        )

    monkeypatch.setenv("SCHEMA_SENTRY_API_KEY", "airflow-secret")
    monkeypatch.setattr(schema_sentry_client, "urlopen", blocking_urlopen)

    response = schema_sentry_client.post_json(
        "/api/v1/pipelines/daily_revenue/validate",
        {},
    )

    assert response.status == 409
    assert response.body == {"safe": False}


def test_guard_raises_on_409(monkeypatch: pytest.MonkeyPatch) -> None:
    import daily_revenue

    def blocking_response(path: str, payload: dict[str, str]) -> StubResponse:
        assert path == "/api/v1/pipelines/daily_revenue/validate"
        assert payload == {}
        return StubResponse(409, {"safe": False})

    monkeypatch.setattr(daily_revenue, "post_json", blocking_response)

    with pytest.raises(AirflowFailException, match="blocking schema drift"):
        daily_revenue.validate_pipeline("daily_revenue")


def test_guard_accepts_safe_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    import daily_revenue

    monkeypatch.setattr(
        daily_revenue,
        "post_json",
        lambda _path, _payload: StubResponse(200, {"safe": True}),
    )

    daily_revenue.validate_pipeline("daily_revenue")


@pytest.mark.parametrize("body", [{}, {"safe": None}, {"safe": False}])
def test_guard_rejects_any_response_not_explicitly_safe(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, Any],
) -> None:
    import daily_revenue

    monkeypatch.setattr(
        daily_revenue,
        "post_json",
        lambda _path, _payload: StubResponse(200, body),
    )

    with pytest.raises(AirflowFailException, match="blocking schema drift"):
        daily_revenue.validate_pipeline("daily_revenue")


def test_revenue_sql_is_idempotent() -> None:
    import daily_revenue

    normalized = " ".join(daily_revenue.AGGREGATE_DAILY_REVENUE_SQL.split()).upper()

    assert "SUM(AMOUNT)" in normalized
    assert "ON CONFLICT (DATE) DO UPDATE" in normalized
