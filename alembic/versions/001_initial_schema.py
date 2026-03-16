"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("signing_secret", sa.String(255), nullable=False),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="5"),
        sa.Column("retry_backoff_base", sa.Float, nullable=False, server_default="2.0"),
        sa.Column("retry_max_delay_seconds", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default="30"),
        sa.Column("event_types_filter", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("custom_headers", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "endpoint_id",
            UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webhook_events_endpoint_id", "webhook_events", ["endpoint_id"])
    op.create_index("ix_webhook_events_event_type", "webhook_events", ["event_type"])
    op.create_index("ix_webhook_events_status", "webhook_events", ["status"])
    op.create_index(
        "ix_webhook_events_retry",
        "webhook_events",
        ["status", "next_retry_at"],
        postgresql_where=sa.text("status = 'failed'"),
    )

    op.create_table(
        "delivery_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("webhook_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("request_headers", JSONB, nullable=False, server_default="{}"),
        sa.Column("request_body_hash", sa.String(64), nullable=True),
        sa.Column("http_status_code", sa.Integer, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("response_headers", JSONB, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Float, nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_delivery_attempts_event_id", "delivery_attempts", ["event_id"])

    op.create_table(
        "dead_letter_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("webhook_events.id"),
            nullable=False,
        ),
        sa.Column("endpoint_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_payload", JSONB, nullable=False),
        sa.Column("event_type", sa.String(255), nullable=True),
        sa.Column("total_attempts", sa.Integer, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_http_status", sa.Integer, nullable=True),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "dead_lettered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_dead_letter_events_endpoint_id", "dead_letter_events", ["endpoint_id"])


def downgrade() -> None:
    op.drop_table("dead_letter_events")
    op.drop_table("delivery_attempts")
    op.drop_table("webhook_events")
    op.drop_table("webhook_endpoints")
