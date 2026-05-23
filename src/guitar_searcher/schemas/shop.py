from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class ShopClassification(StrEnum):
    MAJOR_RETAILER = "major_retailer"
    BOUTIQUE = "boutique"
    VINTAGE_SPECIALIST = "vintage_specialist"
    UNKNOWN = "unknown"
    DEAD = "dead"


class InventoryStrategy(StrEnum):
    REVERB_API = "reverb_api"
    DEDICATED_SCRAPER = "dedicated_scraper"
    SHOPIFY_JSON = "shopify_json"
    GENERIC_CRAWLER = "generic_crawler"
    EMAIL_ONLY = "email_only"
    MANUAL = "manual"
    NONE = "none"


class Shop(BaseModel):
    """Pydantic view of a shop, used for seed loading and API responses."""

    name: str
    domain: str
    website_url: HttpUrl

    reverb_shop_slug: str | None = None
    email: str | None = None
    phone: str | None = None

    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    timezone: str | None = Field(
        default=None,
        description="IANA tz, e.g. 'America/Indiana/Indianapolis'. Never inferred from state.",
    )

    classification: ShopClassification = ShopClassification.UNKNOWN
    inventory_strategy: InventoryStrategy = InventoryStrategy.NONE
    scraper_module: str | None = Field(
        default=None,
        description="Importable module path under guitar_searcher.scrapers, e.g. 'sweetwater'.",
    )

    notes: str | None = None
    active: bool = True
