from __future__ import annotations

import pytest

from guitar_searcher.db.session import get_session
from guitar_searcher.matching.fingerprint import fingerprint_listing
from guitar_searcher.matching.score import ScoredListing
from guitar_searcher.models.notifications import NotifiedListingRow
from guitar_searcher.schemas import Condition, ListingSource, NormalizedListing, QuerySpec
from guitar_searcher.watch_runner import (
    add_watch,
    already_notified_fingerprints,
    list_watches,
    record_notifications,
    remove_watch,
    set_watch_active,
)


def _listing(uid: str = "x") -> NormalizedListing:
    listing = NormalizedListing(
        source=ListingSource.SHOP_DIRECT,
        source_listing_id=uid,
        shop_name="Shop",
        shop_domain="shop.test",
        brand="Fender",
        model="Jaguar",
        year=1962,
        finish="sunburst",
        condition=Condition.EXCELLENT,
        price_usd=24500,
        url=f"https://shop.test/p/{uid}",
        raw_title=f"1962 Fender Jaguar #{uid}",
    )
    listing.fingerprint = fingerprint_listing(listing)
    return listing


def test_add_list_remove_watch(tmp_db: str) -> None:
    with get_session() as s:
        row = add_watch(s, name="jag-hunt", query=QuerySpec(brand="Fender", model="Jaguar"), cadence="daily")
        wid = row.id

    with get_session() as s:
        watches = list_watches(s, only_active=True)
        assert any(w.id == wid for w in watches)

    with get_session() as s:
        set_watch_active(s, wid, False)
    with get_session() as s:
        assert all(w.id != wid for w in list_watches(s, only_active=True))

    with get_session() as s:
        remove_watch(s, wid)
    with get_session() as s:
        assert all(w.id != wid for w in list_watches(s))


def test_bad_cadence_rejected(tmp_db: str) -> None:
    with pytest.raises(ValueError), get_session() as s:
        add_watch(s, name="x", query=QuerySpec(), cadence="every-second")


def test_notification_dedup(tmp_db: str) -> None:
    with get_session() as s:
        watch = add_watch(s, name="t", query=QuerySpec(brand="Fender"), cadence="daily")
        wid = watch.id

    # Initially nothing notified.
    with get_session() as s:
        assert already_notified_fingerprints(s, wid) == set()

    # Record one notification.
    m = ScoredListing(listing=_listing("a"), score=0.9, reasoning="match")
    with get_session() as s:
        record_notifications(s, wid, [m])

    with get_session() as s:
        fps = already_notified_fingerprints(s, wid)
        assert _listing("a").fingerprint in fps


def test_notification_unique_per_watch(tmp_db: str) -> None:
    """The same fingerprint can be notified for two different watches."""
    with get_session() as s:
        w1 = add_watch(s, name="t1", query=QuerySpec(), cadence="daily").id
        w2 = add_watch(s, name="t2", query=QuerySpec(), cadence="daily").id

    m = ScoredListing(listing=_listing("a"), score=0.9, reasoning="match")
    with get_session() as s:
        record_notifications(s, w1, [m])
        record_notifications(s, w2, [m])

    with get_session() as s:
        rows = s.query(NotifiedListingRow).all()
        assert len(rows) == 2
