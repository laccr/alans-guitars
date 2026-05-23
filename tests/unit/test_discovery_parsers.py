"""Pure parser tests for OSM + Reverb shop-detail JSON. No network."""
from __future__ import annotations

from guitar_searcher.discovery.osm import _shop_from_osm
from guitar_searcher.discovery.reverb_directory import _shop_from_reverb
from guitar_searcher.schemas.shop import InventoryStrategy


def test_reverb_us_shop_parses() -> None:
    data = {
        "name": "Test Vintage",
        "slug": "test-vintage",
        "legal_country_code": "US",
        "address": {"region": "TN", "locality": "Nashville", "country_code": "US"},
        "website": "https://testvintage.com",
        "description": "A short description",
        "on_vacation": False,
    }
    shop = _shop_from_reverb(data)
    assert shop is not None
    assert shop.name == "Test Vintage"
    assert shop.reverb_shop_slug == "test-vintage"
    assert shop.state == "TN"
    assert shop.city == "Nashville"
    assert shop.domain == "testvintage.com"
    assert shop.inventory_strategy == InventoryStrategy.REVERB_API
    assert shop.discovered_from == "reverb_directory"


def test_reverb_non_us_skipped() -> None:
    data = {
        "name": "London Shop",
        "slug": "london",
        "legal_country_code": "GB",
        "address": {"country_code": "GB"},
    }
    assert _shop_from_reverb(data) is None


def test_reverb_on_vacation_skipped() -> None:
    data = {
        "name": "Vacation Shop",
        "slug": "vacation",
        "legal_country_code": "US",
        "on_vacation": True,
    }
    assert _shop_from_reverb(data) is None


def test_reverb_no_website_falls_back_to_reverb_url() -> None:
    data = {
        "name": "No Site",
        "slug": "no-site",
        "legal_country_code": "US",
        "website": None,
    }
    shop = _shop_from_reverb(data)
    assert shop is not None
    assert "reverb.com/shop/no-site" in str(shop.website_url)


def test_osm_node_with_website() -> None:
    element = {
        "type": "node",
        "id": 12345,
        "lat": 36.16,
        "lon": -86.77,
        "tags": {
            "shop": "musical_instruments",
            "name": "Nashville Guitar Co",
            "website": "https://nashguitarco.com",
            "phone": "+1-615-555-0100",
            "addr:city": "Nashville",
            "addr:state": "TN",
            "addr:street": "Main St",
            "addr:housenumber": "100",
        },
    }
    shop = _shop_from_osm(element)
    assert shop is not None
    assert shop.name == "Nashville Guitar Co"
    assert shop.phone == "+1-615-555-0100"
    assert shop.city == "Nashville"
    assert shop.street == "100 Main St"
    assert shop.discovered_from == "osm"
    assert shop.active is False  # discovered shops require manual activation
    assert shop.inventory_strategy == InventoryStrategy.EMAIL_ONLY


def test_osm_unnamed_skipped() -> None:
    element = {"type": "node", "id": 1, "tags": {"shop": "musical_instruments"}}
    assert _shop_from_osm(element) is None


def test_osm_no_website_falls_back_to_osm_url() -> None:
    element = {
        "type": "node",
        "id": 999,
        "tags": {"name": "Tiny Music Shop", "shop": "musical_instruments"},
    }
    shop = _shop_from_osm(element)
    assert shop is not None
    assert "openstreetmap.org" in str(shop.website_url)
    assert shop.domain.startswith("osm.")
