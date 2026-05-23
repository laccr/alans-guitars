from __future__ import annotations

import hashlib
import re

from guitar_searcher.schemas import NormalizedListing


def _slug(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _price_bucket(price: float | None) -> str:
    """Round to 5% bucket so cross-source price drift doesn't break dedup."""
    if not price:
        return "x"
    if price <= 0:
        return "x"
    bucket = round(price / max(50.0, price * 0.05))
    return str(bucket)


def fingerprint_listing(listing: NormalizedListing) -> str:
    """Stable hash for cross-source dedup.

    Two listings sharing a fingerprint are likely the same physical guitar — same shop,
    brand, model family, year, price bucket. Serial-number-aware when present.
    """
    if listing.serial_number:
        key = f"sn:{_slug(listing.serial_number)}|{_slug(listing.brand)}|{_slug(listing.model)}"
    else:
        key = "|".join(
            [
                _slug(listing.shop_domain or listing.shop_name),
                _slug(listing.brand),
                _slug(listing.model),
                str(listing.year or "x"),
                _price_bucket(listing.price_usd),
            ]
        )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()
