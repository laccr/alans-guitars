"""add discovered_from + last_verified_at to shops

Revision ID: 20260523_0200
Revises: 20260523_0100
Create Date: 2026-05-23

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260523_0200"
down_revision: str | None = "20260523_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("shops") as batch:
        batch.add_column(sa.Column("discovered_from", sa.String(32), nullable=True))
        batch.add_column(sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_shops_discovered_from", "shops", ["discovered_from"])


def downgrade() -> None:
    op.drop_index("ix_shops_discovered_from", table_name="shops")
    with op.batch_alter_table("shops") as batch:
        batch.drop_column("last_verified_at")
        batch.drop_column("discovered_from")
