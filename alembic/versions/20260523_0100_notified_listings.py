"""notified_listings table for watch dedup

Revision ID: 20260523_0100
Revises: 20260522_0000
Create Date: 2026-05-23

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260523_0100"
down_revision: str | None = "20260522_0000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notified_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "search_id",
            sa.Integer(),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("listing_url", sa.String(1024), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("search_id", "fingerprint", name="uq_notified_search_fp"),
    )
    op.create_index("ix_notified_search", "notified_listings", ["search_id"])


def downgrade() -> None:
    op.drop_index("ix_notified_search", table_name="notified_listings")
    op.drop_table("notified_listings")
