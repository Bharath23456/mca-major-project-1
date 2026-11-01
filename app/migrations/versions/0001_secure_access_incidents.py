"""Add secure-access, incident, and audit tables.

Revision ID: 0001_secure_access_incidents
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0001_secure_access_incidents"
down_revision = None
branch_labels = None
depends_on = None


def _create_monitoring_tables_if_missing() -> None:
    inspector = inspect(op.get_bind())
    if "anomaly_events" not in inspector.get_table_names():
        op.create_table(
            "anomaly_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("detector", sa.String(length=32), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("metrics_json", sa.Text(), nullable=False),
        )
        op.create_index("ix_anomaly_events_created_at", "anomaly_events", ["created_at"])

    if "alert_events" not in inspector.get_table_names():
        op.create_table(
            "alert_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("fingerprint", sa.String(length=128), nullable=False),
            sa.Column("alertname", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False, server_default="unknown"),
            sa.Column("instance", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("starts_at", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("ends_at", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("labels_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_alert_events_alertname", "alert_events", ["alertname"])
        op.create_index("ix_alert_events_status", "alert_events", ["status"])
        op.create_index("ix_alert_events_updated_at", "alert_events", ["updated_at"])
        op.create_index("ix_alert_events_fingerprint", "alert_events", ["fingerprint"], unique=True)


def upgrade() -> None:
    _create_monitoring_tables_if_missing()
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('ADMIN', 'OPERATOR', 'VIEWER')", name="ck_users_role"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_login_attempts_key_time", "login_attempts", ["key_hash", "attempted_at"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("affected_target", sa.String(length=512), nullable=False),
        sa.Column("assigned_operator_id", sa.Integer(), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')", name="ck_incidents_status"
        ),
        sa.CheckConstraint(
            "severity IN ('critical', 'warning', 'info', 'unknown')",
            name="ck_incidents_severity",
        ),
        sa.ForeignKeyConstraint(["assigned_operator_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_assigned_operator_id", "incidents", ["assigned_operator_id"])
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])
    op.create_index("ix_incidents_updated_at", "incidents", ["updated_at"])

    op.create_table(
        "incident_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("alert_event_id", sa.Integer(), nullable=True),
        sa.Column("anomaly_event_id", sa.Integer(), nullable=True),
        sa.Column("correlation_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(alert_event_id IS NOT NULL AND anomaly_event_id IS NULL) OR "
            "(alert_event_id IS NULL AND anomaly_event_id IS NOT NULL)",
            name="ck_incident_events_one_source",
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["alert_event_id"], ["alert_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["anomaly_event_id"], ["anomaly_events.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("alert_event_id", name="uq_incident_events_alert"),
        sa.UniqueConstraint("anomaly_event_id", name="uq_incident_events_anomaly"),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])

    op.create_table(
        "incident_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_incident_notes_incident_id", "incident_notes", ["incident_id"])
    op.create_index("ix_incident_notes_author_user_id", "incident_notes", ["author_user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("incident_id", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_incident_id", "audit_logs", ["incident_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_incident_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_incident_notes_author_user_id", table_name="incident_notes")
    op.drop_index("ix_incident_notes_incident_id", table_name="incident_notes")
    op.drop_table("incident_notes")
    op.drop_index("ix_incident_events_incident_id", table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_index("ix_incidents_updated_at", table_name="incidents")
    op.drop_index("ix_incidents_created_at", table_name="incidents")
    op.drop_index("ix_incidents_assigned_operator_id", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_login_attempts_key_time", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_token_hash", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
