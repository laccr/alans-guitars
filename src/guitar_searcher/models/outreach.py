from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from guitar_searcher.models.base import Base, TimestampMixin
from guitar_searcher.models.shop import ShopRow


class OutreachAttemptRow(Base, TimestampMixin):
    __tablename__ = "outreach_attempts"
    __table_args__ = (
        Index("ix_outreach_shop_sent", "shop_id", "sent_at"),
        Index("ix_outreach_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    search_id: Mapped[int | None] = mapped_column(
        ForeignKey("searches.id", ondelete="SET NULL"), nullable=True
    )

    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="email")
    template_id: Mapped[str] = mapped_column(String(64), nullable=False, default="initial_inquiry")

    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    message_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    from_addr: Mapped[str] = mapped_column(String(255), nullable=False)
    to_addr: Mapped[str] = mapped_column(String(255), nullable=False)
    message_id_header: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    shop: Mapped[ShopRow] = relationship(ShopRow, lazy="joined")
    replies: Mapped[list[OutreachReplyRow]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class OutreachReplyRow(Base, TimestampMixin):
    __tablename__ = "outreach_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("outreach_attempts.id", ondelete="CASCADE"), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_body: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="unclear")
    extracted_listings_json: Mapped[list[dict] | None] = mapped_column(  # type: ignore[type-arg]
        JSON, nullable=True
    )
    follow_up_needed: Mapped[bool] = mapped_column(default=False, nullable=False)

    attempt: Mapped[OutreachAttemptRow] = relationship(back_populates="replies")


class OptOutRow(Base, TimestampMixin):
    __tablename__ = "opt_outs"
    __table_args__ = (UniqueConstraint("shop_id", name="uq_opt_outs_shop"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="reply")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
