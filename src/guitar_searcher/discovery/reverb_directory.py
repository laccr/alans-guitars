"""Discover US guitar shops by harvesting unique shop slugs from Reverb listings.

Reverb has no public `/api/shops` index endpoint, so we walk a series of broad listings
queries, collect the unique `shop.slug` values that appear, then fetch shop details for
each. Filtering to US-based shops happens after the detail call (we need
`legal_country_code` to be reliable).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from guitar_searcher.config import get_settings
from guitar_searcher.schemas.shop import InventoryStrategy, Shop, ShopClassification
from guitar_searcher.utils.logging import get_logger
from guitar_searcher.utils.ratelimit import HostRateLimiter

log = get_logger(__name__)

_LISTINGS_URL = "https://api.reverb.com/api/listings"
_SHOP_URL = "https://api.reverb.com/api/shops/{slug}"

# Broad queries chosen to surface a diverse spread of US guitar shops.
DEFAULT_SEED_QUERIES: tuple[str, ...] = (
    "vintage guitar",
    "fender",
    "gibson",
    "martin",
    "boutique guitar",
    "used guitar",
    "guitar amplifier",
)

_PER_PAGE = 50
_MAX_PAGES_PER_QUERY = 4


@dataclass
class DiscoveryResult:
    fetched_listings: int = 0
    shops_examined: int = 0
    us_shops: list[Shop] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.us_shops is None:
            self.us_shops = []


async def discover_reverb_shops(
    *,
    seed_queries: tuple[str, ...] = DEFAULT_SEED_QUERIES,
    max_unique_shops: int = 500,
) -> DiscoveryResult:
    """Walk Reverb listings to find US guitar shops. Returns Shop objects (not persisted)."""
    settings = get_settings()
    token = settings.reverb_token
    if not token:
        raise RuntimeError("REVERB_TOKEN not configured")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/hal+json",
        "Accept-Version": "3.0",
        "User-Agent": settings.user_agent,
    }
    rate_limiter = HostRateLimiter(rps=settings.per_host_rps)
    result = DiscoveryResult()
    seen_slugs: set[str] = set()

    async with httpx.AsyncClient(http2=True, headers=headers, timeout=30) as client:
        for q in seed_queries:
            if len(seen_slugs) >= max_unique_shops:
                break
            for page in range(1, _MAX_PAGES_PER_QUERY + 1):
                if len(seen_slugs) >= max_unique_shops:
                    break
                params: dict[str, str | int] = {
                    "query": q,
                    "per_page": _PER_PAGE,
                    "item_country": "US",
                    "page": page,
                }
                await rate_limiter.acquire(_LISTINGS_URL)
                try:
                    resp = await client.get(_LISTINGS_URL, params=params)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("reverb_dir.listings_failed", query=q, page=page, error=str(exc))
                    break
                listings = resp.json().get("listings", [])
                if not listings:
                    break
                result.fetched_listings += len(listings)
                for raw in listings:
                    slug = (raw.get("shop") or {}).get("slug")
                    if slug and slug not in seen_slugs:
                        seen_slugs.add(slug)

        log.info("reverb_dir.collected_slugs", count=len(seen_slugs))

        for slug in list(seen_slugs)[:max_unique_shops]:
            await rate_limiter.acquire(_SHOP_URL.format(slug=slug))
            try:
                resp = await client.get(_SHOP_URL.format(slug=slug))
                if resp.status_code != 200:
                    continue
                shop_data: dict[str, Any] = resp.json()
            except httpx.HTTPError as exc:
                log.debug("reverb_dir.shop_failed", slug=slug, error=str(exc))
                continue
            result.shops_examined += 1
            shop = _shop_from_reverb(shop_data)
            if shop is not None:
                result.us_shops.append(shop)

    log.info(
        "reverb_dir.complete",
        listings=result.fetched_listings,
        examined=result.shops_examined,
        us_shops=len(result.us_shops),
    )
    return result


def _shop_from_reverb(data: dict[str, Any]) -> Shop | None:
    legal_cc = data.get("legal_country_code")
    address = data.get("address") or {}
    addr_cc = address.get("country_code")
    if legal_cc != "US" and addr_cc != "US":
        return None
    if data.get("on_vacation"):
        return None

    slug = data.get("slug")
    name = data.get("name")
    if not slug or not name:
        return None

    website = (data.get("website") or "").strip()
    domain = _domain_from(website) or f"reverb.com/shop/{slug}"
    website_url = website or f"https://reverb.com/shop/{slug}"

    return Shop(
        name=name,
        domain=domain,
        website_url=website_url,
        reverb_shop_slug=slug,
        email=None,
        phone=None,
        city=address.get("locality"),
        state=address.get("region"),
        postal_code=None,
        timezone=None,
        classification=ShopClassification.UNKNOWN,
        inventory_strategy=InventoryStrategy.REVERB_API,
        scraper_module=None,
        notes=(data.get("description") or "")[:300] or None,
        active=True,
        discovered_from="reverb_directory",
        last_verified_at=datetime.now(UTC),
    )


def _domain_from(url: str) -> str | None:
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None
