"""Shared base for HTML-search scrapers.

Each subclass provides:
- a search URL template
- an optional CSS selector for product cards on the search results page
- field extractors that fall back through: JSON-LD Product → OpenGraph → CSS heuristics

Tuning against fixtures is expected — but the layered fallbacks make these scrapers
useful even before live tuning.
"""
from __future__ import annotations

import json
import re
from abc import abstractmethod
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

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
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)


class HtmlSearchScraper(AbstractScraper):
    """Common search-page parsing for shop-bound scrapers."""

    #: e.g. "https://example.com/search?q={q}"
    search_url_template: str = ""
    #: CSS selector for individual product anchors/cards.
    product_card_selector: str = "a"
    #: Optional CSS selector for the product detail JSON-LD blocks on a card.
    jsonld_selector: str = 'script[type="application/ld+json"]'
    #: Selector for price text inside a card (best-effort fallback).
    price_selector: str = ".price, [class*='price']"
    #: Max product detail pages to fetch per search.
    max_detail_pages: int = 12

    shop_name: str = ""
    shop_domain: str = ""

    async def search(
        self, query: QuerySpec, ctx: ScraperContext, shop: Shop | None = None
    ) -> ScraperResult:
        search_url = self._build_search_url(query)
        if not search_url:
            return ScraperResult(scraper_name=self.name, error="empty search URL")

        headers = {"User-Agent": ctx.user_agent, "Accept": "text/html,application/xhtml+xml"}
        try:
            await ctx.rate_limiter.acquire(search_url)
            resp = await ctx.client.get(
                search_url, headers=headers, timeout=ctx.timeout_s, follow_redirects=True
            )
            if resp.status_code >= 400:
                return ScraperResult(
                    scraper_name=self.name,
                    error=f"search returned {resp.status_code}",
                )
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:
            log.warning(f"{self.name}.search_error", error=str(exc))
            return ScraperResult(scraper_name=self.name, error=str(exc))

        product_urls = self._extract_product_urls(soup, base_url=str(resp.url))[: self.max_detail_pages]

        listings: list[NormalizedListing] = []
        examined = 0
        for url in product_urls:
            examined += 1
            try:
                await ctx.rate_limiter.acquire(url)
                page = await ctx.client.get(
                    url, headers=headers, timeout=ctx.timeout_s, follow_redirects=True
                )
                if page.status_code >= 400:
                    continue
                listing = self._parse_detail(page.text, url, shop)
                if listing:
                    listings.append(listing)
            except Exception as exc:
                log.debug(f"{self.name}.detail_skip", url=url, error=str(exc))
                continue

        return ScraperResult(scraper_name=self.name, listings=listings, examined=examined)

    @abstractmethod
    def _build_search_url(self, query: QuerySpec) -> str:
        raise NotImplementedError

    def _extract_product_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        cards = soup.select(self.product_card_selector)
        urls: list[str] = []
        seen: set[str] = set()
        for card in cards:
            href = card.get("href") if isinstance(card, Tag) else None
            if isinstance(href, str) and href:
                full = urljoin(base_url, href)
                if self._looks_like_product_url(full) and full not in seen:
                    seen.add(full)
                    urls.append(full)
        return urls

    def _looks_like_product_url(self, url: str) -> bool:
        """Override in subclass for site-specific filtering. Default accepts everything on-domain."""
        parsed = urlparse(url)
        if not parsed.hostname:
            return False
        return self.shop_domain in parsed.hostname

    def _parse_detail(
        self, html: str, url: str, shop: Shop | None
    ) -> NormalizedListing | None:
        soup = BeautifulSoup(html, "html.parser")
        data = _extract_jsonld_product(soup)
        title = _extract_title(soup, data)
        if not title:
            return None
        description = _extract_description(soup, data)
        price = _extract_price(soup, data)
        images = _extract_images(soup, data, base_url=url)

        norm = normalize_title(title, description)

        shop_name = (shop.name if shop else None) or self.shop_name
        shop_domain = (shop.domain if shop else None) or self.shop_domain

        listing = NormalizedListing(
            source=ListingSource.SHOP_DIRECT,
            source_listing_id=f"{shop_domain}:{_hash_url(url)}",
            shop_name=shop_name,
            shop_domain=shop_domain,
            brand=norm.brand,
            model=norm.model,
            year=norm.year,
            year_confidence=norm.year_confidence,
            finish=norm.finish,
            color=None,
            condition=Condition.UNKNOWN,
            price_usd=price,
            currency="USD",
            url=url,
            image_urls=images,
            raw_title=title,
            raw_description=(description or "")[:2000] or None,
        )
        listing.fingerprint = fingerprint_listing(listing)
        return listing


# ─── Generic extractors (work across most modern e-commerce sites) ──────────


def _extract_jsonld_product(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _iter_jsonld(payload):
            if isinstance(item, dict) and _is_product_schema(item):
                return item
    return None


def _iter_jsonld(payload: Any) -> Any:
    if isinstance(payload, list):
        for entry in payload:
            yield from _iter_jsonld(entry)
    elif isinstance(payload, dict):
        if "@graph" in payload and isinstance(payload["@graph"], list):
            yield from _iter_jsonld(payload["@graph"])
        else:
            yield payload


def _is_product_schema(item: dict[str, Any]) -> bool:
    t = item.get("@type")
    if isinstance(t, list):
        return any(x == "Product" for x in t)
    return t == "Product"


def _extract_title(soup: BeautifulSoup, jsonld: dict[str, Any] | None) -> str | None:
    if jsonld and jsonld.get("name"):
        return str(jsonld["name"]).strip()
    og = soup.find("meta", property="og:title")
    if isinstance(og, Tag) and og.get("content"):
        return str(og["content"]).strip()
    h1 = soup.find("h1")
    if h1 and h1.text:
        return str(h1.text).strip()
    if soup.title and soup.title.text:
        return str(soup.title.text).strip()
    return None


def _extract_description(
    soup: BeautifulSoup, jsonld: dict[str, Any] | None
) -> str | None:
    if jsonld and jsonld.get("description"):
        return str(jsonld["description"]).strip()
    og = soup.find("meta", property="og:description")
    if isinstance(og, Tag) and og.get("content"):
        return str(og["content"]).strip()
    md = soup.find("meta", attrs={"name": "description"})
    if isinstance(md, Tag) and md.get("content"):
        return str(md["content"]).strip()
    return None


_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d{2})?)")


def _extract_price(soup: BeautifulSoup, jsonld: dict[str, Any] | None) -> float | None:
    if jsonld:
        offer = jsonld.get("offers")
        if isinstance(offer, list) and offer:
            offer = offer[0]
        if isinstance(offer, dict):
            price = offer.get("price") or offer.get("lowPrice")
            try:
                return float(str(price).replace(",", "")) if price is not None else None
            except (TypeError, ValueError):
                pass
    # Meta tag fallback
    for meta_prop in ("product:price:amount", "og:price:amount"):
        meta = soup.find("meta", property=meta_prop)
        if isinstance(meta, Tag) and meta.get("content"):
            try:
                return float(str(meta["content"]).replace(",", ""))
            except ValueError:
                continue
    # Body text fallback
    body_text = soup.get_text(" ", strip=True)[:4000]
    match = _PRICE_RE.search(body_text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _extract_images(
    soup: BeautifulSoup, jsonld: dict[str, Any] | None, base_url: str
) -> list[str]:
    images: list[str] = []
    if jsonld:
        img = jsonld.get("image")
        if isinstance(img, str):
            images.append(img)
        elif isinstance(img, list):
            images.extend(str(x) for x in img if isinstance(x, str))
    if not images:
        og = soup.find("meta", property="og:image")
        if isinstance(og, Tag) and og.get("content"):
            images.append(str(og["content"]))
    return [urljoin(base_url, i) for i in images[:5]]


def _hash_url(url: str) -> str:
    import hashlib

    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
