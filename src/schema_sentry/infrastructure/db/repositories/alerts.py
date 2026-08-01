from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from schema_sentry.application.notification_service import (
    AlertChangeContext,
    DeliveryRecord,
    ScanAlertContext,
)
from schema_sentry.domain.enums import AlertStatus, ScanStatus, Severity
from schema_sentry.domain.models import CanonicalType
from schema_sentry.infrastructure.db.models import (
    AlertDeliveryModel,
    DatasetModel,
    DataSourceModel,
    LineageEdgeModel,
    PipelineModel,
    ScanRunModel,
    SchemaChangeModel,
)


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, delivery: AlertDeliveryModel) -> AlertDeliveryModel:
        self.session.add(delivery)
        self.session.flush()
        return delivery

    def list_for_scan(self, scan_id: UUID) -> tuple[AlertDeliveryModel, ...]:
        statement = (
            select(AlertDeliveryModel)
            .where(AlertDeliveryModel.scan_id == scan_id)
            .order_by(AlertDeliveryModel.created_at, AlertDeliveryModel.id)
        )
        return tuple(self.session.scalars(statement))

    def list_dispatchable_for_scan(self, scan_id: UUID) -> tuple[UUID, ...]:
        statement = (
            select(AlertDeliveryModel.id)
            .where(
                AlertDeliveryModel.scan_id == scan_id,
                AlertDeliveryModel.status == AlertStatus.PENDING,
            )
            .order_by(AlertDeliveryModel.created_at, AlertDeliveryModel.id)
        )
        return tuple(self.session.scalars(statement))

    def lock_delivery(self, delivery_id: UUID) -> DeliveryRecord | None:
        delivery = self.session.scalar(
            select(AlertDeliveryModel).where(AlertDeliveryModel.id == delivery_id).with_for_update()
        )
        return self._record(delivery) if delivery else None

    def get_scan_context(self, scan_id: UUID) -> ScanAlertContext | None:
        row = self.session.execute(
            select(ScanRunModel, DataSourceModel)
            .join(DataSourceModel, ScanRunModel.source_id == DataSourceModel.id)
            .where(ScanRunModel.id == scan_id)
        ).one_or_none()
        if row is None:
            return None
        scan, source = row
        change_rows = self.session.execute(
            select(SchemaChangeModel, DatasetModel)
            .join(DatasetModel, SchemaChangeModel.dataset_id == DatasetModel.id)
            .where(
                SchemaChangeModel.scan_id == scan_id,
                SchemaChangeModel.severity != Severity.INFO,
            )
            .order_by(
                DatasetModel.schema_name,
                DatasetModel.table_name,
                SchemaChangeModel.column_name,
            )
        ).tuples()
        changes = tuple(
            AlertChangeContext(
                qualified_column=(
                    f"{dataset.schema_name}.{dataset.table_name}.{change.column_name}"
                ),
                before_type=self._render_type(change.before_json),
                after_type=self._render_type(change.after_json),
                severity=change.severity,
                affected_dags=self._affected_dags(change),
            )
            for change, dataset in change_rows
        )
        return ScanAlertContext(
            scan_id=scan.id,
            source_key=source.key,
            error_code=scan.error_code if scan.status is ScanStatus.FAILED else None,
            changes=changes,
        )

    def latest_failed_scan_id(self, source_key: str) -> UUID | None:
        statement = (
            select(ScanRunModel.id)
            .join(DataSourceModel, ScanRunModel.source_id == DataSourceModel.id)
            .where(
                DataSourceModel.key == source_key,
                ScanRunModel.status == ScanStatus.FAILED,
            )
            .order_by(ScanRunModel.started_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def mark_attempt_started(self, delivery_id: UUID, attempted_at: datetime) -> DeliveryRecord:
        delivery = self._delivery(delivery_id)
        delivery.attempt_count += 1
        delivery.status = AlertStatus.PENDING
        delivery.next_retry_at = None
        self.session.flush()
        return self._record(delivery)

    def mark_sent(
        self,
        delivery_id: UUID,
        provider_message_id: str | None,
        sent_at: datetime,
    ) -> None:
        delivery = self._delivery(delivery_id)
        delivery.status = AlertStatus.SENT
        delivery.provider_message_id = provider_message_id
        delivery.last_error = None
        delivery.next_retry_at = None
        delivery.sent_at = sent_at
        self.session.flush()

    def mark_failed(
        self,
        delivery_id: UUID,
        error: str,
        next_retry_at: datetime,
    ) -> None:
        delivery = self._delivery(delivery_id)
        delivery.status = AlertStatus.FAILED
        delivery.last_error = error
        delivery.next_retry_at = next_retry_at
        self.session.flush()

    def _delivery(self, delivery_id: UUID) -> AlertDeliveryModel:
        delivery = self.session.get(AlertDeliveryModel, delivery_id)
        if delivery is None:
            raise LookupError(f"alert delivery not found: {delivery_id}")
        return delivery

    def _affected_dags(self, change: SchemaChangeModel) -> tuple[str, ...]:
        statement = (
            select(PipelineModel.airflow_dag_id)
            .join(LineageEdgeModel, LineageEdgeModel.pipeline_id == PipelineModel.id)
            .where(
                LineageEdgeModel.upstream_dataset_id == change.dataset_id,
                LineageEdgeModel.upstream_column == change.column_name,
            )
            .order_by(PipelineModel.airflow_dag_id)
        )
        return tuple(self.session.scalars(statement))

    @staticmethod
    def _render_type(payload: dict[str, Any] | None) -> str | None:
        if payload is None or not isinstance(payload.get("data_type"), dict):
            return None
        return CanonicalType(**payload["data_type"]).render()

    @staticmethod
    def _record(delivery: AlertDeliveryModel) -> DeliveryRecord:
        return DeliveryRecord(
            id=delivery.id,
            scan_id=delivery.scan_id,
            channel=delivery.channel,
            status=delivery.status,
            attempt_count=delivery.attempt_count,
            next_retry_at=delivery.next_retry_at,
        )
