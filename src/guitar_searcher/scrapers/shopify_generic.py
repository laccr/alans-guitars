"""Generic Shopify /products.json scraper.

Many small/boutique guitar shops are on Shopify and expose a JSON catalog at
`/products.json` with pagination. This single scraper covers any seeded shop whose
`inventory_strategy` is `shopify_json`.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

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

_PAGE_SIZE = 250
_MAX_PAGES = 6


@register_scraper
class ShopifyGenericScraper(AbstractScraper):
    name = "shopify_generic"
    display = "Shopify (/products.json)"
    is_generic = False  # bound to a shop per invocation

    async def search(
        self, query: QuerySpec, ctx: ScraperContext, shop: Shop | None = None
    ) -> ScraperResult:
        if shop is None:
            return ScraperResult(scraper_name=self.name, error="shopify scraper requires a shop")

        base = str(shop.website_url).rstrip("/")
        listings: list[NormalizedListing] = []
        examined = 0
        headers = {"User-Agent": ctx.user_agent, "Accept": "application/json"}

        try:
            for page in range(1, _MAX_PAGES + 1):
                url = f"{base}/products.json?limit={_PAGE_SIZE}&page={page}"
                await ctx.rate_limiter.acquire(url)
                resp = await ctx.client.get(url, headers=headers, timeout=ctx.timeout_s)
                if resp.status_code == 404:
                    return ScraperResult(
                        scraper_name=self.name,
                        error=f"{shop.domain} does not expose /products.json (404)",
                    )
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "json" not in ct:
                    return ScraperResult(
                        scraper_name=self.name, error=f"{shop.domain} returned non-JSON ({ct})"
                    )
                data: dict[str, Any] = resp.json()
                products = data.get("products", [])
                if not products:
                    break
                examined += len(products)
                for product in products:
                    parsed = self._parse_product(product, shop, base)
                    if parsed and self._is_guitar_like(parsed):
                        listings.append(parsed)
                if len(products) < _PAGE_SIZE:
                    break
        except Exception as exc:
            log.warning("shopify_generic.error", shop=shop.domain, error=str(exc))
            return ScraperResult(
                scraper_name=self.name,
                listings=listings,
                examined=examined,
                error=str(exc),
            )

        return ScraperResult(scraper_name=self.name, listings=listings, examined=examined)

    def _parse_product(
        self, product: dict[str, Any], shop: Shop, base_url: str
    ) -> NormalizedListing | None:
        try:
            title = product.get("title", "")
            handle = product.get("handle")
            if not handle:
                return None
            product_url = urljoin(base_url + "/", f"products/{handle}")

            description_html = product.get("body_html") or ""
            description = _strip_html(description_html)

            variants: list[dict[str, Any]] = product.get("variants", []) or []
            price_usd: float | None = None
            available = False
            for v in variants:
                if v.get("available"):
                    available = True
                price_raw = v.get("price")
                if price_raw is None:
                    continue
                try:
                    p = float(price_raw)
                except (TypeError, ValueError):
                    continue
                if price_usd is None or p < price_usd:
                    price_usd = p
            if not available and variants:
                return None  # sold out

            norm = normalize_title(title, description)
            product_type = (product.get("product_type") or "").lower()
            vendor = product.get("vendor")

            # Hard-reject obvious non-guitar product categories.
            _non_guitar_types = (
                "string",
                "strings",
                "accessor",
                "case",
                "pedal",
                "amp",
                "cable",
                "strap",
                "pick",
                "tuner",
                "stand",
                "capo",
                "apparel",
                "merch",
            )
            if any(bad in product_type for bad in _non_guitar_types):
                return None

            images = []
            for img in product.get("images", [])[:5]:
                src = img.get("src")
                if src:
                    images.append(src)

            listing = NormalizedListing(
                source=ListingSource.SHOP_DIRECT,
                source_listing_id=f"{shop.domain}:{product.get('id')}",
                shop_name=shop.name,
                shop_domain=shop.domain,
                brand=norm.brand or vendor,
                model=norm.model,
                year=norm.year,
                year_confidence=norm.year_confidence,
                finish=norm.finish,
                color=None,
                condition=Condition.UNKNOWN,
                price_usd=price_usd,
                currency="USD",
                url=product_url,
                image_urls=images,
                raw_title=f"{vendor} {title}".strip() if vendor else title,
                raw_description=description[:2000] if description else None,
            )
            listing.fingerprint = fingerprint_listing(listing)
            return listing
        except Exception as exc:
            log.debug("shopify_generic.parse_skip", error=str(exc))
            return None

    @staticmethod
    def _is_guitar_like(listing: NormalizedListing) -> bool:
        haystack = " ".join(
            [listing.raw_title.lower(), (listing.raw_description or "").lower()[:500]]
        )
        bad = ("strap", "string set", "picks", "tuner", "pedal", "amp", "cable", "case", "stand")
        guitar_words = ("guitar", "telecaster", "stratocaster", "les paul")
        has_bad = any(b in haystack for b in bad)
        has_guitar = any(g in haystack for g in guitar_words)
        return not (has_bad and not has_guitar)


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text
