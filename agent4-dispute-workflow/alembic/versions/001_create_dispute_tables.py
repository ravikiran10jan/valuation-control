"""create dispute workflow tables

Revision ID: 001_dispute_tables
Revises:
Create Date: 2026-02-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_dispute_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── disputes ──────────────────────────────────────────────
    op.create_table(
        "disputes",
        sa.Column("dispute_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exception_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False, server_default="INITIATED"),
        sa.Column("vc_position", sa.Text(), nullable=True),
        sa.Column("desk_position", sa.Text(), nullable=True),
        sa.Column("vc_analyst", sa.String(100), nullable=False),
        sa.Column("desk_trader", sa.String(100), nullable=True),
        sa.Column("desk_mark", sa.Numeric(18, 2), nullable=True),
        sa.Column("vc_fair_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("difference", sa.Numeric(18, 2), nullable=True),
        sa.Column("difference_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("resolution_type", sa.String(30), nullable=True),
        sa.Column("final_mark", sa.Numeric(18, 2), nullable=True),
        sa.Column("audit_trail", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_date",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("resolved_date", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("dispute_id"),
    )
    op.create_index("ix_disputes_exception_id", "disputes", ["exception_id"])
    op.create_index("ix_disputes_position_id", "disputes", ["position_id"])
    op.create_index("ix_disputes_state", "disputes", ["state"])

    # ── dispute_messages ──────────────────────────────────────
    op.create_table(
        "dispute_messages",
        sa.Column("message_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column("sender", sa.String(100), nullable=False),
        sa.Column("sender_role", sa.String(10), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("attachments", postgresql.JSONB(), nullable=True),
        sa.Column(
            "source", sa.String(20), nullable=False, server_default="platform"
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["dispute_id"], ["disputes.dispute_id"]),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_dispute_messages_dispute_id", "dispute_messages", ["dispute_id"]
    )

    # ── dispute_approvals ─────────────────────────────────────
    op.create_table(
        "dispute_approvals",
        sa.Column("approval_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(100), nullable=False),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("old_mark", sa.Numeric(18, 2), nullable=False),
        sa.Column("new_mark", sa.Numeric(18, 2), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="PENDING"
        ),
        sa.Column(
            "requested_date",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("approved_date", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dispute_id"], ["disputes.dispute_id"]),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index(
        "ix_dispute_approvals_dispute_id", "dispute_approvals", ["dispute_id"]
    )

    # ── dispute_attachments ───────────────────────────────────
    op.create_table(
        "dispute_attachments",
        sa.Column("attachment_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dispute_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("s3_key", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("document_type", sa.String(50), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uploaded_by", sa.String(100), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["dispute_id"], ["disputes.dispute_id"]),
        sa.PrimaryKeyConstraint("attachment_id"),
    )
    op.create_index(
        "ix_dispute_attachments_dispute_id", "dispute_attachments", ["dispute_id"]
    )


def downgrade() -> None:
    op.drop_table("dispute_attachments")
    op.drop_table("dispute_approvals")
    op.drop_table("dispute_messages")
    op.drop_table("disputes")
