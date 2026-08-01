from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Protocol
from uuid import UUID

from schema_sentry.domain.enums import AlertChannel, AlertStatus, Severity


class DeliveryFailure(RuntimeError):
    pass


class DeliveryNotFound(LookupError):
    def __init__(self, delivery_id: UUID) -> None:
        super().__init__(f"alert delivery not found: {delivery_id}")


class MaxAttemptsExceeded(RuntimeError):
    def __init__(self, delivery_id: UUID) -> None:
        super().__init__(f"maximum delivery attempts exceeded: {delivery_id}")


class RetryNotDue(RuntimeError):
    def __init__(self, next_retry_at: datetime) -> None:
        self.next_retry_at = next_retry_at
        super().__init__(f"alert retry is not due until: {next_retry_at.isoformat()}")


@dataclass(frozen=True, slots=True)
class AlertMessage:
    subject: str
    text: str
    html: str
    dashboard_url: str


@dataclass(frozen=True, slots=True)
class ProviderReceipt:
    provider_message_id: str | None


@dataclass(frozen=True, slots=True)
class AlertChangeContext:
    qualified_column: str
    before_type: str | None
    after_type: str | None
    severity: Severity
    affected_dags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScanAlertContext:
    scan_id: UUID
    source_key: str
    error_code: str | None
    changes: tuple[AlertChangeContext, ...]


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    id: UUID
    scan_id: UUID
    channel: AlertChannel
    status: AlertStatus
    attempt_count: int
    next_retry_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    delivery_id: UUID
    channel: AlertChannel
    success: bool
    attempt_count: int
    next_retry_at: datetime | None


class Notifier(Protocol):
    channel: AlertChannel

    def send(self, message: AlertMessage) -> ProviderReceipt: ...


class AlertPersistence(Protocol):
    def list_dispatchable_for_scan(self, scan_id: UUID) -> tuple[UUID, ...]: ...

    def lock_delivery(self, delivery_id: UUID) -> DeliveryRecord | None: ...

    def get_scan_context(self, scan_id: UUID) -> ScanAlertContext | None: ...

    def latest_failed_scan_id(self, source_key: str) -> UUID | None: ...

    def mark_attempt_started(self, delivery_id: UUID, attempted_at: datetime) -> DeliveryRecord: ...

    def mark_sent(
        self, delivery_id: UUID, provider_message_id: str | None, sent_at: datetime
    ) -> None: ...

    def mark_failed(self, delivery_id: UUID, error: str, next_retry_at: datetime) -> None: ...


def build_alert_message(context: ScanAlertContext, dashboard_base_url: str) -> AlertMessage:
    dashboard_url = f"{dashboard_base_url.rstrip('/')}/"
    if context.error_code:
        subject = f"Schema Sentry source failure: {context.source_key}"
        lines = [
            subject,
            f"scan #{context.scan_id}",
            f"error: {context.error_code}",
            f"dashboard: {dashboard_url}",
        ]
    else:
        subject = f"Schema Sentry drift detected: {context.source_key}"
        lines = [subject, f"scan #{context.scan_id}"]
        for change in context.changes:
            transition = f"{change.before_type or '∅'} → {change.after_type or '∅'}"
            dags = ", ".join(change.affected_dags) or "no registered DAG"
            lines.append(
                f"[{change.severity.value}] {change.qualified_column}: "
                f"{transition}; affected: {dags}"
            )
        lines.append(f"dashboard: {dashboard_url}")
    text = "\n".join(lines)
    html = "<br>".join(escape(line) for line in lines)
    return AlertMessage(subject=subject, text=text, html=html, dashboard_url=dashboard_url)


class NotificationService:
    RETRY_DELAYS = (60, 300, 900)

    def __init__(
        self,
        repository: AlertPersistence,
        notifiers: tuple[Notifier, ...],
        *,
        dashboard_base_url: str,
    ) -> None:
        self.repository = repository
        self.notifiers = {notifier.channel: notifier for notifier in notifiers}
        self.dashboard_base_url = dashboard_base_url

    def dispatch_scan(
        self, scan_id: UUID, *, now: datetime | None = None
    ) -> tuple[DeliveryResult, ...]:
        attempted_at = now or datetime.now(UTC)
        return tuple(
            self._attempt(delivery_id, attempted_at)
            for delivery_id in self.repository.list_dispatchable_for_scan(scan_id)
        )

    def dispatch_system_error(
        self, scan_id: UUID, *, now: datetime | None = None
    ) -> tuple[DeliveryResult, ...]:
        return self.dispatch_scan(scan_id, now=now)

    def retry(self, delivery_id: UUID, *, now: datetime | None = None) -> DeliveryResult:
        return self._attempt(delivery_id, now or datetime.now(UTC))

    def _attempt(self, delivery_id: UUID, now: datetime) -> DeliveryResult:
        delivery = self.repository.lock_delivery(delivery_id)
        if delivery is None:
            raise DeliveryNotFound(delivery_id)
        if delivery.attempt_count >= len(self.RETRY_DELAYS):
            raise MaxAttemptsExceeded(delivery_id)
        if delivery.next_retry_at and now < delivery.next_retry_at:
            raise RetryNotDue(delivery.next_retry_at)
        context = self.repository.get_scan_context(delivery.scan_id)
        if context is None:
            raise DeliveryNotFound(delivery_id)
        notifier = self.notifiers.get(delivery.channel)
        if notifier is None:
            raise DeliveryFailure("notification_channel_not_configured")

        attempted = self.repository.mark_attempt_started(delivery_id, now)
        message = build_alert_message(context, self.dashboard_base_url)
        try:
            receipt = notifier.send(message)
        except DeliveryFailure as exc:
            next_retry_at = now + timedelta(seconds=self.RETRY_DELAYS[attempted.attempt_count - 1])
            self.repository.mark_failed(delivery_id, str(exc), next_retry_at)
            return DeliveryResult(
                delivery_id=delivery_id,
                channel=delivery.channel,
                success=False,
                attempt_count=attempted.attempt_count,
                next_retry_at=next_retry_at,
            )
        self.repository.mark_sent(delivery_id, receipt.provider_message_id, now)
        return DeliveryResult(
            delivery_id=delivery_id,
            channel=delivery.channel,
            success=True,
            attempt_count=attempted.attempt_count,
            next_retry_at=None,
        )
