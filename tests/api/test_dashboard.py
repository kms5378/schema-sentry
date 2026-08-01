import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl

from schema_sentry.application.change_service import BaselineVersionConflict
from schema_sentry.application.query_service import (
    PersistedChange,
    PersistedDelivery,
    PersistedScan,
)
from schema_sentry.config import Settings
from schema_sentry.domain.enums import (
    AlertChannel,
    AlertStatus,
    ChangeState,
    ChangeType,
    ScanStatus,
    ScanTrigger,
    Severity,
)
from schema_sentry.domain.models import DatasetRef
from tests.api.conftest import ApiFakes


@pytest.fixture
def dashboard_scan(api_fakes: ApiFakes) -> PersistedScan:
    change_id = uuid4()
    scan = PersistedScan(
        id=uuid4(),
        source_key="game",
        current_baseline_version=7,
        trigger=ScanTrigger.SCHEDULED,
        status=ScanStatus.COMPLETED,
        started_at=datetime(2026, 8, 1, 1, 2, 3, tzinfo=UTC),
        finished_at=datetime(2026, 8, 1, 1, 2, 4, tzinfo=UTC),
        duration_ms=1000,
        error_code=None,
        error_message=None,
        changes=(
            PersistedChange(
                id=change_id,
                dataset=DatasetRef("public", "purchases"),
                column_name="amount",
                change_type=ChangeType.TYPE_CHANGE,
                severity=Severity.BREAKING,
                state=ChangeState.OPEN,
                before={"data_type": {"name": "numeric", "precision": 12, "scale": 2}},
                after={"data_type": {"name": "text"}},
                affected_dags=("daily_revenue",),
            ),
        ),
        deliveries=(
            PersistedDelivery(
                id=uuid4(),
                channel=AlertChannel.SLACK,
                status=AlertStatus.SENT,
                attempt_count=1,
                provider_message_id="slack-1",
                last_error=None,
                next_retry_at=None,
                sent_at=datetime(2026, 8, 1, 1, 2, 5, tzinfo=UTC),
            ),
        ),
    )
    api_fakes.query.result = scan
    return scan


def test_dashboard_shows_change_impact(
    client: TestClient,
    dashboard_scan: PersistedScan,
) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "public.purchases.amount" in response.text
    assert "BREAKING" in response.text
    assert "daily_revenue" in response.text
    assert "Slack: SENT" in response.text
    assert str(dashboard_scan.id) in response.text
    assert 'aria-live="polite"' in response.text


def test_dashboard_static_assets_are_local(client: TestClient) -> None:
    page = client.get("/")

    assert 'src="/static/htmx.min.js"' in page.text
    assert 'href="/static/app.css"' in page.text
    assert '"code":"409"' in page.text
    assert '"code":"404","swap":true' in page.text
    assert '"code":"503","swap":true' in page.text
    htmx = client.get("/static/htmx.min.js")
    assert htmx.status_code == 200
    assert (
        hashlib.sha256(htmx.content).hexdigest()
        == "71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de"
    )
    assert client.get("/static/app.css").status_code == 200
    assert page.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]


def test_run_scan_action_uses_scan_service(
    client: TestClient,
    api_headers: dict[str, str],
    api_fakes: ApiFakes,
    dashboard_scan: PersistedScan,
) -> None:
    response = client.post(
        "/actions/scans",
        data={"source_key": "game"},
        headers=api_headers,
    )

    assert response.status_code == 200
    assert api_fakes.scan.source_keys == ["game"]
    assert "public.purchases.amount" in response.text


def test_accept_action_requires_operator_identity(
    client: TestClient,
    dashboard_scan: PersistedScan,
) -> None:
    change = dashboard_scan.changes[0]

    response = client.post(
        f"/actions/changes/{change.id}/accept",
        data={"baseline_version": dashboard_scan.current_baseline_version},
    )

    assert response.status_code == 401


def test_accept_action_refreshes_change_list(
    client: TestClient,
    api_headers: dict[str, str],
    api_fakes: ApiFakes,
    dashboard_scan: PersistedScan,
) -> None:
    change = dashboard_scan.changes[0]

    response = client.post(
        f"/actions/changes/{change.id}/accept",
        data={"baseline_version": dashboard_scan.current_baseline_version},
        headers=api_headers,
    )

    assert response.status_code == 200
    assert api_fakes.change.accepted == [(change.id, 7)]
    assert 'id="changes-panel"' in response.text


def test_dashboard_actions_reject_cross_origin_requests(
    client: TestClient,
    api_headers: dict[str, str],
    dashboard_scan: PersistedScan,
) -> None:
    response = client.post(
        "/actions/scans",
        data={"source_key": "game"},
        headers={**api_headers, "Origin": "https://attacker.example"},
    )

    assert response.status_code == 403


def test_proxy_authenticated_action_requires_same_origin(
    client: TestClient,
    settings: Settings,
    dashboard_scan: PersistedScan,
) -> None:
    settings.trust_proxy_auth = True
    without_origin = client.post(
        "/actions/scans",
        data={"source_key": "game"},
        headers={"X-Authenticated-User": "portfolio-owner"},
    )
    same_origin = client.post(
        "/actions/scans",
        data={"source_key": "game"},
        headers={
            "X-Authenticated-User": "portfolio-owner",
            "Origin": "http://testserver",
        },
    )

    assert without_origin.status_code == 403
    assert same_origin.status_code == 200


def test_proxy_action_uses_configured_https_public_origin(
    client: TestClient,
    settings: Settings,
    dashboard_scan: PersistedScan,
) -> None:
    settings.trust_proxy_auth = True
    settings.dashboard_base_url = AnyHttpUrl("https://schema.example/")

    response = client.post(
        "/actions/scans",
        data={"source_key": "game"},
        headers={
            "X-Authenticated-User": "portfolio-owner",
            "Origin": "https://schema.example",
        },
    )

    assert response.status_code == 200


def test_accept_conflict_returns_visible_refresh_message(
    client: TestClient,
    api_headers: dict[str, str],
    api_fakes: ApiFakes,
    dashboard_scan: PersistedScan,
) -> None:
    change = dashboard_scan.changes[0]
    api_fakes.change.error = BaselineVersionConflict(expected=7, actual=8)

    response = client.post(
        f"/actions/changes/{change.id}/accept",
        data={"baseline_version": 7},
        headers=api_headers,
    )

    assert response.status_code == 409
    assert "refresh" in response.text.lower()
    assert "version 8" in response.text.lower()
