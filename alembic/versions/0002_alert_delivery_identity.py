"""Prevent duplicate channel deliveries for one scan.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "alert_delivery_identity",
        "alert_deliveries",
        ["scan_id", "channel"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "alert_delivery_identity",
        "alert_deliveries",
        type_="unique",
    )
