from __future__ import annotations

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from guitar_searcher.models.base import Base, TimestampMixin


class ShopRow(Base, TimestampMixin):
    __tablename__ = "shops"
    __table_args__ = (UniqueConstraint("domain", name="uq_shops_domain"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website_url: Mapped[str] = mapped_column(String(512), nullable=False)

    reverb_shop_slug: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    inventory_strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    scraper_module: Mapped[str | None] = mapped_column(String(128), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
