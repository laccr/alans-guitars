"""Test the generic HTML extractors against a synthesized product detail page.

This is the structural test for HtmlSearchScraper — does our JSON-LD / OG / heuristic
pipeline produce a NormalizedListing from a representative product page?
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from guitar_searcher.scrapers._html_search import (
    _extract_description,
    _extract_jsonld_product,
    _extract_price,
    _extract_title,
)

PRODUCT_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta property="og:title" content="1962 Fender Jaguar Sunburst" />
<meta property="og:description" content="All-original 1962 Fender Jaguar in 3-tone sunburst. Plays beautifully." />
<meta property="og:image" content="https://example.com/img.jpg" />
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "1962 Fender Jaguar Sunburst",
  "description": "All-original 1962 Fender Jaguar in 3-tone sunburst.",
  "image": "https://example.com/img.jpg",
  "offers": {
    "@type": "Offer",
    "price": "24500.00",
    "priceCurrency": "USD"
  }
}
</script>
</head>
<body><h1>1962 Fender Jaguar Sunburst</h1></body>
</html>
"""


def test_jsonld_extracts_product() -> None:
    soup = BeautifulSoup(PRODUCT_HTML, "html.parser")
    data = _extract_jsonld_product(soup)
    assert data is not None
    assert data["name"] == "1962 Fender Jaguar Sunburst"


def test_title_via_jsonld() -> None:
    soup = BeautifulSoup(PRODUCT_HTML, "html.parser")
    data = _extract_jsonld_product(soup)
    assert _extract_title(soup, data) == "1962 Fender Jaguar Sunburst"


def test_price_via_jsonld() -> None:
    soup = BeautifulSoup(PRODUCT_HTML, "html.parser")
    data = _extract_jsonld_product(soup)
    assert _extract_price(soup, data) == 24500.00


def test_description_via_jsonld() -> None:
    soup = BeautifulSoup(PRODUCT_HTML, "html.parser")
    data = _extract_jsonld_product(soup)
    desc = _extract_description(soup, data)
    assert desc and "sunburst" in desc.lower()


def test_fallback_to_og_when_no_jsonld() -> None:
    html = """
    <html><head>
    <meta property="og:title" content="Gibson Les Paul Standard 1959">
    <meta property="og:description" content="Vintage Gibson.">
    <meta property="product:price:amount" content="450000">
    </head><body></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    data = _extract_jsonld_product(soup)
    assert data is None
    assert _extract_title(soup, data) == "Gibson Les Paul Standard 1959"
    assert _extract_price(soup, data) == 450000.0
