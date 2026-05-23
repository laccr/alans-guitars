from __future__ import annotations

import httpx
import pytest
import respx

from guitar_searcher.schemas import QuerySpec
from guitar_searcher.schemas.shop import InventoryStrategy, Shop, ShopClassification
from guitar_searcher.scrapers.base import ScraperContext
from guitar_searcher.scrapers.shopify_generic import ShopifyGenericScraper
from guitar_searcher.utils.ratelimit import HostRateLimiter

PRODUCTS_RESP_PAGE1 = {
    "products": [
        {
            "id": 11111,
            "title": "1962 Fender Jaguar Sunburst",
            "handle": "1962-fender-jaguar-sunburst",
            "vendor": "Fender",
            "product_type": "Electric Guitar",
            "body_html": "<p>All-original 1962 Fender Jaguar in 3-tone sunburst.</p>",
            "variants": [{"available": True, "price": "24500.00"}],
            "images": [{"src": "https://cdn.shop.test/img/jaguar.jpg"}],
        },
        {
            "id": 22222,
            "title": "Set of strings",
            "handle": "strings",
            "vendor": "Ernie Ball",
            "product_type": "Strings",
            "body_html": "",
            "variants": [{"available": True, "price": "8.00"}],
            "images": [],
        },
        {
            "id": 33333,
            "title": "Gibson Les Paul Standard 1959 Reissue",
            "handle": "gibson-lp-1959-reissue",
            "vendor": "Gibson",
            "product_type": "Electric Guitar",
            "body_html": "<p>Custom Shop reissue.</p>",
            "variants": [{"available": True, "price": "8200.00"}],
            "images": [{"src": "https://cdn.shop.test/img/lp.jpg"}],
        },
    ]
}

PRODUCTS_RESP_EMPTY = {"products": []}


@pytest.mark.asyncio
async def test_shopify_scraper_parses_products() -> None:
    shop = Shop(
        name="Test Shop",
        domain="shop.test",
        website_url="https://shop.test",
        classification=ShopClassification.BOUTIQUE,
        inventory_strategy=InventoryStrategy.SHOPIFY_JSON,
    )

    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://shop.test", assert_all_called=False) as mock:
            mock.get("/products.json", params={"limit": "250", "page": "1"}).respond(
                200,
                json=PRODUCTS_RESP_PAGE1,
                headers={"content-type": "application/json"},
            )

            ctx = ScraperContext(
                client=client,
                rate_limiter=HostRateLimiter(rps=100),
                user_agent="test/1.0",
            )
            result = await ShopifyGenericScraper().search(QuerySpec(), ctx, shop)

    assert result.error is None, result.error
    assert result.examined == 3
    # "strings" filtered out as not-guitar-like; Jaguar + LP remain.
    titles = [l.raw_title for l in result.listings]
    assert any("Jaguar" in t for t in titles)
    assert any("Les Paul" in t for t in titles)
    assert not any("strings" in t.lower() for t in titles)


@pytest.mark.asyncio
async def test_shopify_scraper_handles_404() -> None:
    shop = Shop(
        name="Not Shopify",
        domain="notshopify.test",
        website_url="https://notshopify.test",
        classification=ShopClassification.BOUTIQUE,
        inventory_strategy=InventoryStrategy.SHOPIFY_JSON,
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://notshopify.test") as mock:
            mock.get("/products.json", params={"limit": "250", "page": "1"}).respond(404)
            ctx = ScraperContext(
                client=client,
                rate_limiter=HostRateLimiter(rps=100),
                user_agent="test/1.0",
            )
            result = await ShopifyGenericScraper().search(QuerySpec(), ctx, shop)
    assert result.error is not None
    assert "404" in result.error
    assert result.listings == []
