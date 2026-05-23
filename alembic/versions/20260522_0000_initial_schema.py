"""initial schema

Revision ID: 20260522_0000
Revises:
Create Date: 2026-05-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260522_0000"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("website_url", sa.String(512), nullable=False),
        sa.Column("reverb_shop_slug", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("postal_code", sa.String(32), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("classification", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("inventory_strategy", sa.String(32), nullable=False, server_default="none"),
        sa.Column("scraper_module", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint("domain", name="uq_shops_domain"),
    )
    op.create_index("ix_shops_domain", "shops", ["domain"])
    op.create_index("ix_shops_reverb_shop_slug", "shops", ["reverb_shop_slug"])

    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_listing_id", sa.String(128), nullable=False),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="SET NULL"), nullable=True),
        sa.Column("brand", sa.String(128), nullable=True),
        sa.Column("model", sa.String(256), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("year_confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("finish", sa.String(128), nullable=True),
        sa.Column("color", sa.String(64), nullable=True),
        sa.Column("condition", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("price_usd", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("image_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("raw_title", sa.String(512), nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=True),
        sa.Column("serial_number", sa.String(64), nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint("source", "source_listing_id", name="uq_listings_source_id"),
    )
    op.create_index("ix_listings_brand", "listings", ["brand"])
    op.create_index("ix_listings_model", "listings", ["model"])
    op.create_index("ix_listings_shop_seen", "listings", ["shop_id", "last_seen_at"])
    op.create_index("ix_listings_fingerprint", "listings", ["fingerprint"])

    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("query_spec_json", sa.JSON(), nullable=False),
        sa.Column("is_watch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("watch_cadence", sa.String(32), nullable=True),
        sa.Column("watch_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
    )

    op.create_table(
        "search_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_id", sa.Integer(), sa.ForeignKey("searches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shops_queried", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_examined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_run_id", sa.Integer(), sa.ForeignKey("search_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_matches_run_score", "matches", ["search_run_id", "score"])


def downgrade() -> None:
    op.drop_index("ix_matches_run_score", table_name="matches")
    op.drop_table("matches")
    op.drop_table("search_runs")
    op.drop_table("searches")
    op.drop_index("ix_listings_fingerprint", table_name="listings")
    op.drop_index("ix_listings_shop_seen", table_name="listings")
    op.drop_index("ix_listings_model", table_name="listings")
    op.drop_index("ix_listings_brand", table_name="listings")
    op.drop_table("listings")
    op.drop_index("ix_shops_reverb_shop_slug", table_name="shops")
    op.drop_index("ix_shops_domain", table_name="shops")
    op.drop_table("shops")
