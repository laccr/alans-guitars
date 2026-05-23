from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class ListingSource(StrEnum):
    REVERB_API = "reverb_api"
    SHOP_DIRECT = "shop_direct"
    OUTREACH_REPLY = "outreach_reply"


class Condition(StrEnum):
    NEW = "new"
    BSTOCK = "b_stock"
    MINT = "mint"
    EXCELLENT = "excellent"
    VERY_GOOD = "very_good"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    NON_FUNCTIONING = "non_functioning"
    USED = "used"
    UNKNOWN = "unknown"


class NormalizedListing(BaseModel):
    """Lingua franca that every scraper emits and the matcher consumes."""

    source: ListingSource
    source_listing_id: str = Field(description="Stable per-source ID for dedup within a source.")

    shop_name: str
    shop_domain: str | None = None
    shop_id: int | None = Field(
        default=None,
        description="DB id once persisted; scrapers may leave this None.",
    )

    brand: str | None = None
    model: str | None = None
    year: int | None = None
    year_confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    finish: str | None = None
    color: str | None = None
    condition: Condition = Condition.UNKNOWN

    price_usd: float | None = None
    currency: str = "USD"

    url: HttpUrl
    image_urls: list[HttpUrl] = Field(default_factory=list)

    raw_title: str
    raw_description: str | None = None

    serial_number: str | None = None

    seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    fingerprint: str | None = Field(
        default=None,
        description="Cross-source dedup hash. Populated by matching.fingerprint.",
    )
