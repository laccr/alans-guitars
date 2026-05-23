"""Elderly Instruments scraper."""
from __future__ import annotations

from urllib.parse import quote, urlparse

from guitar_searcher.schemas import QuerySpec
from guitar_searcher.scrapers._html_search import HtmlSearchScraper
from guitar_searcher.scrapers.registry import register_scraper


@register_scraper
class ElderlyScraper(HtmlSearchScraper):
    name = "elderly"
    display = "Elderly Instruments"
    shop_name = "Elderly Instruments"
    shop_domain = "elderly.com"

    search_url_template = "https://www.elderly.com/search?q={q}"
    product_card_selector = "a.product-card, a[href*='/products/'], h3 a"
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
        return "/products/" in parsed.path or "/items/" in parsed.path
