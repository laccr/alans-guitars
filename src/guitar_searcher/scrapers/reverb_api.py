"""Tier A — Reverb official Listings API.

Docs: https://www.reverb-api.com / https://reverb.com/page/api-docs

Requires REVERB_TOKEN in environment. Without it the scraper short-circuits to an empty result.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from guitar_searcher.config import get_settings
from guitar_searcher.matching.fingerprint import fingerprint_listing
from guitar_searcher.matching.normalize import normalize_title
from guitar_searcher.schemas import (
    Condition,
    ListingSource,
    NormalizedListing,
    QuerySpec,
    Shop,
)
from guitar_searcher.scrapers.base import AbstractScraper, ScraperContext, ScraperResult
from guitar_searcher.scrapers.registry import register_scraper
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://api.reverb.com/api"
_LISTINGS_PATH = "/listings"
_PAGE_SIZE = 50
_MAX_PAGES = 4

_REVERB_CONDITION_MAP: dict[str, Condition] = {
    "brand-new": Condition.NEW,
    "b-stock": Condition.BSTOCK,
    "mint": Condition.MINT,
    "excellent": Condition.EXCELLENT,
    "very-good": Condition.VERY_GOOD,
    "good": Condition.GOOD,
    "fair": Condition.FAIR,
    "poor": Condition.POOR,
    "non-functioning": Condition.NON_FUNCTIONING,
    "used": Condition.USED,
}


@register_scraper
class ReverbApiScraper(AbstractScraper):
    name = "reverb_api"
    display = "Reverb API"
    is_generic = True  # runs once per search regardless of shop binding

    async def search(
        self, query: QuerySpec, ctx: ScraperContext, shop: Shop | None = None
    ) -> ScraperResult:
        token = get_settings().reverb_token
        if not token:
            return ScraperResult(scraper_name=self.name, error="REVERB_TOKEN not configured")

        params = self._to_params(query)
        if shop and shop.reverb_shop_slug:
            params["shop_slug"] = shop.reverb_shop_slug

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/hal+json",
            "Accept-Version": "3.0",
            "User-Agent": ctx.user_agent,
        }

        listings: list[NormalizedListing] = []
        examined = 0
        page = 1
        next_url: str | None = _BASE_URL + _LISTINGS_PATH

        try:
            while next_url and page <= _MAX_PAGES:
                await ctx.rate_limiter.acquire(next_url)
                if page == 1:
                    resp = await ctx.client.get(
                        next_url, params=params, headers=headers, timeout=ctx.timeout_s
                    )
                else:
                    resp = await ctx.client.get(next_url, headers=headers, timeout=ctx.timeout_s)
                if resp.status_code == 401:
                    return ScraperResult(
                        scraper_name=self.name, error="Reverb API unauthorized (check token)"
                    )
                resp.raise_for_status()
                payload: dict[str, Any] = resp.json()
                raw_listings = payload.get("listings", [])
                examined += len(raw_listings)
                for raw in raw_listings:
                    parsed = self._parse_listing(raw)
                    if parsed is not None:
                        listings.append(parsed)

                next_link = payload.get("_links", {}).get("next", {})
                next_url = next_link.get("href")
                page += 1
        except Exception as exc:
            log.warning("reverb_api.error", error=str(exc))
            return ScraperResult(
                scraper_name=self.name,
                listings=listings,
                examined=examined,
                error=str(exc),
            )

        return ScraperResult(scraper_name=self.name, listings=listings, examined=examined)

    @staticmethod
    def _to_params(query: QuerySpec) -> dict[str, Any]:
        terms: list[str] = []
        if query.brand:
            terms.append(query.brand)
        if query.model:
            terms.append(query.model)
        if query.finish:
            terms.append(query.finish)
        terms.extend(query.keywords)
        params: dict[str, Any] = {
            "product_type": "electric-guitars",  # widened below via category filter
            "query": " ".join(terms).strip(),
            "per_page": _PAGE_SIZE,
            "ships_to": "US",
            "item_country": "US",
            "currency": "USD",
        }
        # Drop product_type — Reverb's search handles broader categories via the query string
        params.pop("product_type")
        if query.max_price_usd is not None:
            params["price_max"] = int(query.max_price_usd)
        if query.min_price_usd is not None:
            params["price_min"] = int(query.min_price_usd)
        if query.year_min is not None:
            params["year_min"] = query.year_min
        if query.year_max is not None:
            params["year_max"] = query.year_max
        if query.brand:
            params["make"] = query.brand
        if query.model:
            params["model"] = query.model
        if not params["query"]:
            params.pop("query")
        return params

    def _parse_listing(self, raw: dict[str, Any]) -> NormalizedListing | None:
        try:
            url = raw.get("_links", {}).get("web", {}).get("href")
            if not url:
                return None
            shop = raw.get("shop", {}) or {}
            shop_name = shop.get("name") or "Reverb seller"
            shop_url = shop.get("_links", {}).get("web", {}).get("href")
            shop_domain = urlparse(shop_url).hostname if shop_url else "reverb.com"

            title = raw.get("title", "")
            description = raw.get("description")
            norm = normalize_title(title, description)

            price = raw.get("price", {}) or {}
            price_usd: float | None = None
            amount = price.get("amount") if price.get("currency", "USD") == "USD" else None
            if amount is not None:
                try:
                    price_usd = float(amount)
                except (TypeError, ValueError):
                    price_usd = None

            cond_slug = (raw.get("condition") or {}).get("slug") or "used"
            condition = _REVERB_CONDITION_MAP.get(cond_slug, Condition.USED)

            images = []
            for photo in raw.get("photos", [])[:5]:
                href = photo.get("_links", {}).get("full", {}).get("href")
                if href:
                    images.append(href)

            listing = NormalizedListing(
                source=ListingSource.REVERB_API,
                source_listing_id=str(raw.get("id")),
                shop_name=shop_name,
                shop_domain=shop_domain,
                brand=raw.get("make") or norm.brand,
                model=raw.get("model") or norm.model,
                year=self._safe_year(raw.get("year") or norm.year),
                year_confidence=1.0 if raw.get("year") else norm.year_confidence,
                finish=raw.get("finish") or norm.finish,
                color=None,
                condition=condition,
                price_usd=price_usd,
                currency=price.get("currency", "USD"),
                url=url,
                image_urls=images,
                raw_title=title,
                raw_description=description,
            )
            listing.fingerprint = fingerprint_listing(listing)
            return listing
        except Exception as exc:
            log.warning("reverb_api.parse_failed", error=str(exc))
            return None

    @staticmethod
    def _safe_year(value: Any) -> int | None:
        if value is None:
            return None
        try:
            y = int(str(value)[:4])
        except (TypeError, ValueError):
            return None
        return y if 1920 <= y <= 2100 else None
