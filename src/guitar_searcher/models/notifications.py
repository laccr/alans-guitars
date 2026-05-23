from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from guitar_searcher.models.base import Base, TimestampMixin


class NotifiedListingRow(Base, TimestampMixin):
    """Persistent record of which (watch, listing-fingerprint) pairs we've already alerted on.

    Stored separately from MatchRow so that even if matches/search_runs are pruned, the
    dedup signal survives across watch executions.
    """

    __tablename__ = "notified_listings"
    __table_args__ = (
        UniqueConstraint("search_id", "fingerprint", name="uq_notified_search_fp"),
        Index("ix_notified_search", "search_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(
        ForeignKey("searches.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    listing_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
