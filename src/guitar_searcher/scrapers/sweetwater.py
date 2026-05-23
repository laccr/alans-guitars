"""Sweetwater scraper.

Sweetwater is protected by Akamai/Cloudflare bot detection. The MVP attempts a polite
httpx fetch with a real browser-like User-Agent; production should swap to Playwright +
playwright-stealth when this scraper starts returning 403s consistently. The site's product
pages embed JSON-LD Product blocks, so once we reach a detail page extraction is reliable.
"""
from __future__ import annotations

from urllib.parse import quote, urlparse

from guitar_searcher.schemas import QuerySpec
from guitar_searcher.scrapers._html_search import HtmlSearchScraper
from guitar_searcher.scrapers.registry import register_scraper


@register_scraper
class SweetwaterScraper(HtmlSearchScraper):
    name = "sweetwater"
    display = "Sweetwater"
    shop_name = "Sweetwater"
    shop_domain = "sweetwater.com"

    search_url_template = "https://www.sweetwater.com/store/search.php?s={q}"
    product_card_selector = "a.product-card__title, a[class*='product-card'], a[href*='/store/detail/']"
    max_detail_pages = 10

    def _build_search_url(self, query: QuerySpec) -> str:
        terms: list[str] = []
        if query.brand:
            terms.append(query.brand)
        if query.model:
            terms.append(query.model)
        if not terms:
            terms.extend(query.keywords)
        if not terms:
            return ""
        return self.search_url_template.format(q=quote(" ".join(terms)))

    def _looks_like_product_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.hostname or self.shop_domain not in parsed.hostname:
            return False
        return "/store/detail/" in parsed.path
