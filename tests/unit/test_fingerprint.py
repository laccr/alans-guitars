from __future__ import annotations

from guitar_searcher.matching.fingerprint import fingerprint_listing
from guitar_searcher.schemas import Condition, ListingSource, NormalizedListing


def _listing(**kwargs: object) -> NormalizedListing:
    defaults = dict(
        source=ListingSource.SHOP_DIRECT,
        source_listing_id="abc",
        shop_name="Shop A",
        shop_domain="shopa.com",
        brand="Fender",
        model="Jaguar",
        year=1962,
        finish="sunburst",
        condition=Condition.EXCELLENT,
        price_usd=24500.0,
        url="https://shopa.com/p/1",
        raw_title="1962 Fender Jaguar Sunburst",
    )
    defaults.update(kwargs)
    return NormalizedListing(**defaults)  # type: ignore[arg-type]


def test_same_inputs_same_fingerprint() -> None:
    a = _listing()
    b = _listing()
    assert fingerprint_listing(a) == fingerprint_listing(b)


def test_serial_number_dominates() -> None:
    a = _listing(serial_number="L12345", brand="Fender", model="Jaguar")
    b = _listing(serial_number="L12345", brand="Fender", model="Jaguar", price_usd=99999, year=1999)
    assert fingerprint_listing(a) == fingerprint_listing(b)


def test_different_shops_different_fingerprint() -> None:
    a = _listing(shop_domain="shopa.com")
    b = _listing(shop_domain="shopb.com")
    assert fingerprint_listing(a) != fingerprint_listing(b)


def test_small_price_drift_still_matches() -> None:
    a = _listing(price_usd=24500)
    b = _listing(price_usd=24600)  # within 5% bucket
    assert fingerprint_listing(a) == fingerprint_listing(b)
