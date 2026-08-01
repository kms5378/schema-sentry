from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from schema_sentry.application.notification_service import (
    AlertChangeContext,
    AlertMessage,
    DeliveryFailure,
    DeliveryRecord,
    MaxAttemptsExceeded,
    NotificationService,
    ProviderReceipt,
    RetryNotDue,
    ScanAlertContext,
    build_alert_message,
)
from schema_sentry.domain.enums import AlertChannel, AlertStatus, Severity

NOW = datetime(2026, 8, 1, tzinfo=UTC)


class FakeNotifier:
    def __init__(self, channel: AlertChannel, *, fail: bool = False) -> None:
        self.channel = channel
        self.fail = fail
        self.messages: list[AlertMessage] = []

    def send(self, message: AlertMessage) -> ProviderReceipt:
        self.messages.append(message)
        if self.fail:
            raise DeliveryFailure("provider_delivery_failed")
        return ProviderReceipt(provider_message_id="provider-123")


class FakeAlertRepository:
    def __init__(self, delivery: DeliveryRecord, context: ScanAlertContext) -> None:
        self.delivery = delivery
        self.context = context
        self.last_error: str | None = None

    def list_dispatchable_for_scan(self, scan_id):
        return (self.delivery.id,) if scan_id == self.delivery.scan_id else ()

    def lock_delivery(self, delivery_id):
        return self.delivery if delivery_id == self.delivery.id else None

    def get_scan_context(self, scan_id):
        return self.context if scan_id == self.context.scan_id else None

    def latest_failed_scan_id(self, source_key):
        return self.context.scan_id if source_key == self.context.source_key else None

    def mark_attempt_started(self, delivery_id, attempted_at):
        self.delivery = DeliveryRecord(
            id=self.delivery.id,
            scan_id=self.delivery.scan_id,
            channel=self.delivery.channel,
            status=AlertStatus.PENDING,
            attempt_count=self.delivery.attempt_count + 1,
            next_retry_at=None,
        )
        return self.delivery

    def mark_sent(self, delivery_id, provider_message_id, sent_at):
        self.delivery = DeliveryRecord(
            id=self.delivery.id,
            scan_id=self.delivery.scan_id,
            channel=self.delivery.channel,
            status=AlertStatus.SENT,
            attempt_count=self.delivery.attempt_count,
            next_retry_at=None,
        )

    def mark_failed(self, delivery_id, error, next_retry_at):
        self.last_error = error
        self.delivery = DeliveryRecord(
            id=self.delivery.id,
            scan_id=self.delivery.scan_id,
            channel=self.delivery.channel,
            status=AlertStatus.FAILED,
            attempt_count=self.delivery.attempt_count,
            next_retry_at=next_retry_at,
        )


@pytest.fixture
def alert_context() -> ScanAlertContext:
    return ScanAlertContext(
        scan_id=uuid4(),
        source_key="game",
        error_code=None,
        changes=(
            AlertChangeContext(
                qualified_column="public.purchases.amount",
                before_type="numeric(12,2)",
                after_type="character varying",
                severity=Severity.BREAKING,
                affected_dags=("daily_revenue_dag",),
            ),
        ),
    )


def make_delivery(context: ScanAlertContext, *, attempts: int = 0) -> DeliveryRecord:
    return DeliveryRecord(
        id=uuid4(),
        scan_id=context.scan_id,
        channel=AlertChannel.SLACK,
        status=AlertStatus.PENDING,
        attempt_count=attempts,
        next_retry_at=None,
    )


def test_message_contains_actionable_context(alert_context: ScanAlertContext) -> None:
    message = build_alert_message(alert_context, "https://schema.example.com/")

    assert "public.purchases.amount" in message.text
    assert "numeric(12,2) → character varying" in message.text
    assert "daily_revenue_dag" in message.text
    assert f"scan #{alert_context.scan_id}" in message.text
    assert message.dashboard_url.endswith("/")


def test_successful_dispatch_marks_delivery_sent(alert_context: ScanAlertContext) -> None:
    repository = FakeAlertRepository(make_delivery(alert_context), alert_context)
    notifier = FakeNotifier(AlertChannel.SLACK)
    service = NotificationService(
        repository, (notifier,), dashboard_base_url="https://schema.example.com/"
    )

    results = service.dispatch_scan(alert_context.scan_id, now=NOW)

    assert results[0].success is True
    assert repository.delivery.status is AlertStatus.SENT
    assert repository.delivery.attempt_count == 1
    assert len(notifier.messages) == 1


def test_provider_failure_is_recorded_with_retry_time(alert_context: ScanAlertContext) -> None:
    repository = FakeAlertRepository(make_delivery(alert_context), alert_context)
    notifier = FakeNotifier(AlertChannel.SLACK, fail=True)
    service = NotificationService(repository, (notifier,), dashboard_base_url="http://localhost/")

    result = service.dispatch_scan(alert_context.scan_id, now=NOW)[0]

    assert result.success is False
    assert repository.delivery.status is AlertStatus.FAILED
    assert repository.delivery.next_retry_at == NOW + timedelta(seconds=60)
    assert repository.last_error == "provider_delivery_failed"


def test_retry_before_due_time_is_rejected(alert_context: ScanAlertContext) -> None:
    delivery = make_delivery(alert_context, attempts=1)
    delivery = DeliveryRecord(
        id=delivery.id,
        scan_id=delivery.scan_id,
        channel=delivery.channel,
        status=AlertStatus.FAILED,
        attempt_count=1,
        next_retry_at=NOW + timedelta(seconds=60),
    )
    service = NotificationService(
        FakeAlertRepository(delivery, alert_context),
        (FakeNotifier(AlertChannel.SLACK),),
        dashboard_base_url="http://localhost/",
    )

    with pytest.raises(RetryNotDue):
        service.retry(delivery.id, now=NOW)


def test_third_failure_is_final_without_retry_time(alert_context: ScanAlertContext) -> None:
    repository = FakeAlertRepository(make_delivery(alert_context, attempts=2), alert_context)
    service = NotificationService(
        repository,
        (FakeNotifier(AlertChannel.SLACK, fail=True),),
        dashboard_base_url="http://localhost/",
    )

    result = service.retry(repository.delivery.id, now=NOW)

    assert result.success is False
    assert result.attempt_count == 3
    assert result.next_retry_at is None
    assert repository.delivery.next_retry_at is None


def test_fourth_attempt_is_rejected(alert_context: ScanAlertContext) -> None:
    delivery = make_delivery(alert_context, attempts=3)
    service = NotificationService(
        FakeAlertRepository(delivery, alert_context),
        (FakeNotifier(AlertChannel.SLACK),),
        dashboard_base_url="http://localhost/",
    )

    with pytest.raises(MaxAttemptsExceeded):
        service.retry(delivery.id, now=NOW)
