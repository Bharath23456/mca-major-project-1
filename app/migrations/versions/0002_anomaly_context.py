"""Store target and model state with anomaly events.

Revision ID: 0002_anomaly_context
Revises: 0001_secure_access_incidents
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_anomaly_context"
down_revision = "0001_secure_access_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("anomaly_events")}
    if "target" not in columns:
        op.add_column(
            "anomaly_events",
            sa.Column("target", sa.String(length=512), server_default="", nullable=False),
        )
    if "model_status" not in columns:
        op.add_column(
            "anomaly_events",
            sa.Column(
                "model_status",
                sa.String(length=16),
                server_default="unknown",
                nullable=False,
            ),
        )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("anomaly_events")}
    if "model_status" in columns:
        op.drop_column("anomaly_events", "model_status")
    if "target" in columns:
        op.drop_column("anomaly_events", "target")
