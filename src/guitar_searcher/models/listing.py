from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from guitar_searcher.models.base import Base, TimestampMixin
from guitar_searcher.models.shop import ShopRow


class ListingRow(Base, TimestampMixin):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source", "source_listing_id", name="uq_listings_source_id"),
        Index("ix_listings_shop_seen", "shop_id", "last_seen_at"),
        Index("ix_listings_fingerprint", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_listing_id: Mapped[str] = mapped_column(String(128), nullable=False)

    shop_id: Mapped[int | None] = mapped_column(
        ForeignKey("shops.id", ondelete="SET NULL"), nullable=True
    )
    shop: Mapped[ShopRow | None] = relationship(ShopRow, lazy="joined")

    brand: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    finish: Mapped[str | None] = mapped_column(String(128), nullable=True)
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    condition: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    image_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    raw_title: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    serial_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SearchRow(Base, TimestampMixin):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query_spec_json: Mapped[dict] = mapped_column(JSON, nullable=False)  # type: ignore[type-arg]
    is_watch: Mapped[bool] = mapped_column(default=False, nullable=False)
    watch_cadence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    watch_active: Mapped[bool] = mapped_column(default=False, nullable=False)


class SearchRunRow(Base, TimestampMixin):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shops_queried: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    listings_examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MatchRow(Base, TimestampMixin):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_run_score", "search_run_id", "score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    search_run_id: Mapped[int] = mapped_column(
        ForeignKey("search_runs.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified: Mapped[bool] = mapped_column(default=False, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    listing: Mapped[ListingRow] = relationship(ListingRow, lazy="joined")
