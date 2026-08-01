import json

import pytest
import structlog

from schema_sentry.logging import configure_logging, log_source_failure


def test_source_connection_secret_is_redacted_from_json_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = "postgresql+psycopg://reader:super-secret@source-db:5432/game"
    configure_logging("INFO")

    log_source_failure(ValueError(database_url), source_key="game", scan_id="scan-1")

    captured = capsys.readouterr().out
    event = json.loads(captured)
    assert event["event"] == "source_connection_failed"
    assert event["source_key"] == "game"
    assert event["scan_id"] == "scan-1"
    assert event["status"] == "FAILED"
    assert database_url not in captured
    assert "super-secret" not in captured
    assert "[REDACTED]" in event["error"]


def test_sensitive_structured_fields_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")

    structlog.get_logger().info(
        "credentials_loaded",
        api_key="raw-api-key",
        nested={"password": "raw-password", "owner": "analytics"},
        authorization="bearer lowercase-token",
        message="request failed with bearer lowercase-token",
    )

    captured = capsys.readouterr().out
    event = json.loads(captured)
    assert event["api_key"] == "[REDACTED]"
    assert event["nested"] == {"password": "[REDACTED]", "owner": "analytics"}
    assert event["authorization"] == "[REDACTED]"
    assert event["message"] == "request failed with bearer [REDACTED]"
    assert "raw-api-key" not in captured
    assert "raw-password" not in captured
