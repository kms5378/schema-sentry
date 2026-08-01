import json

import structlog


def test_configure_logging_emits_structured_event(capsys) -> None:
    from schema_sentry.logging import configure_logging

    configure_logging("INFO")

    structlog.get_logger().info("scan_finished", scan_id="scan-1", status="COMPLETED")

    event = json.loads(capsys.readouterr().out)
    assert event["event"] == "scan_finished"
    assert event["scan_id"] == "scan-1"
    assert event["status"] == "COMPLETED"
    assert event["level"] == "info"
