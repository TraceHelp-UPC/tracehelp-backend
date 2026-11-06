"""Tablas de diagnósticos RAG (triage_diagnoses) y bitácora inmutable (analytics_audit_logs) (US11, US15, TS07)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06 08:43:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTION_VALUES = (
    "TICKET_REGISTERED",
    "TICKET_STATUS_CHANGED",
    "RAG_RECOMMENDATION_GENERATED",
    "LOW_CONFIDENCE_ALERT_TRIGGERED",
    "AI_RESOLUTION_APPROVED",
    "AI_RESOLUTION_EDITED",
    "AI_RESOLUTION_REJECTED",
    "MANUAL_RESOLUTION_PROVIDED",
    "CLASSIFICATION_OVERRIDDEN",
)

_CONFIDENCE_VALUES = (
    "HIGH_SELF_SERVICE",
    "MEDIUM_ASSISTED",
    "LOW_CONFIDENCE_ALERT",
    "INSUFFICIENT_EVIDENCE",
)

_VALIDATION_VALUES = (
    "PENDING",
    "APPROVED",
    "EDITED",
    "REJECTED",
    "MANUAL_ONLY",
)


def upgrade() -> None:
    op.create_table(
        "triage_diagnoses",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column(
            "confidence_level",
            sa.Enum(
                *_CONFIDENCE_VALUES,
                name="confidence_level",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("has_sufficient_evidence", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_low_confidence_alert", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("suggested_text", sa.Text(), nullable=True),
        sa.Column("final_approved_text", sa.Text(), nullable=True),
        sa.Column(
            "validation_status",
            sa.Enum(
                *_VALIDATION_VALUES,
                name="validation_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.UUID(), nullable=True),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["iam_users.id"],
            name=op.f("fk_triage_diagnoses_reviewer_id_iam_users"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["helpdesk_tickets.id"],
            name=op.f("fk_triage_diagnoses_ticket_id_helpdesk_tickets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["iam_workspaces.id"],
            name=op.f("fk_triage_diagnoses_workspace_id_iam_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_triage_diagnoses")),
    )
    op.create_index("ix_triage_diagnoses_ticket_id", "triage_diagnoses", ["ticket_id"], unique=True)
    op.create_index(
        "ix_triage_diagnoses_workspace_status",
        "triage_diagnoses",
        ["workspace_id", "validation_status"],
        unique=False,
    )

    op.create_table(
        "analytics_audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum(
                *_ACTION_VALUES,
                name="audit_action_type",
                native_enum=False,
                create_constraint=True,
                length=50,
            ),
            nullable=False,
        ),
        sa.Column(
            "consulted_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("validator_analyst_id", sa.UUID(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("integrity_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["helpdesk_tickets.id"],
            name=op.f("fk_analytics_audit_logs_ticket_id_helpdesk_tickets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["validator_analyst_id"],
            ["iam_users.id"],
            name=op.f("fk_analytics_audit_logs_validator_analyst_id_iam_users"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["iam_workspaces.id"],
            name=op.f("fk_analytics_audit_logs_workspace_id_iam_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_audit_logs")),
    )
    op.create_index("ix_analytics_audit_logs_ticket_id", "analytics_audit_logs", ["ticket_id"], unique=False)
    op.create_index(
        "ix_analytics_audit_logs_workspace_occurred",
        "analytics_audit_logs",
        ["workspace_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_audit_logs_workspace_occurred", table_name="analytics_audit_logs")
    op.drop_index("ix_analytics_audit_logs_ticket_id", table_name="analytics_audit_logs")
    op.drop_table("analytics_audit_logs")
    op.drop_index("ix_triage_diagnoses_workspace_status", table_name="triage_diagnoses")
    op.drop_index("ix_triage_diagnoses_ticket_id", table_name="triage_diagnoses")
    op.drop_table("triage_diagnoses")
