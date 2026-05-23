"""outreach_attempts, outreach_replies, opt_outs

Revision ID: 20260523_0300
Revises: 20260523_0200
Create Date: 2026-05-23

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260523_0300"
down_revision: str | None = "20260523_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outreach_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "shop_id",
            sa.Integer(),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "search_id",
            sa.Integer(),
            sa.ForeignKey("searches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(16), nullable=False, server_default="email"),
        sa.Column("template_id", sa.String(64), nullable=False, server_default="initial_inquiry"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("message_html", sa.Text(), nullable=True),
        sa.Column("from_addr", sa.String(255), nullable=False),
        sa.Column("to_addr", sa.String(255), nullable=False),
        sa.Column("message_id_header", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.UniqueConstraint("message_id_header", name="uq_outreach_msgid"),
    )
    op.create_index("ix_outreach_shop_sent", "outreach_attempts", ["shop_id", "sent_at"])
    op.create_index("ix_outreach_status", "outreach_attempts", ["status"])

    op.create_table(
        "outreach_replies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey("outreach_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_body", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False, server_default="unclear"),
        sa.Column("extracted_listings_json", sa.JSON(), nullable=True),
        sa.Column("follow_up_needed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )

    op.create_table(
        "opt_outs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "shop_id",
            sa.Integer(),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False, server_default="reply"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.UniqueConstraint("shop_id", name="uq_opt_outs_shop"),
    )


def downgrade() -> None:
    op.drop_table("opt_outs")
    op.drop_table("outreach_replies")
    op.drop_index("ix_outreach_status", table_name="outreach_attempts")
    op.drop_index("ix_outreach_shop_sent", table_name="outreach_attempts")
    op.drop_table("outreach_attempts")
