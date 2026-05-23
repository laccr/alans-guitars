from __future__ import annotations

import pytest

from guitar_searcher.matching.score import ScoredListing
from guitar_searcher.notifications.email_digest import (
    EmailNotConfigured,
    SmtpSender,
    render_digest,
    send_match_digest,
)
from guitar_searcher.schemas import Condition, ListingSource, NormalizedListing, QuerySpec


def _scored() -> ScoredListing:
    return ScoredListing(
        listing=NormalizedListing(
            source=ListingSource.SHOP_DIRECT,
            source_listing_id="x",
            shop_name="Shop A",
            shop_domain="shop.a",
            brand="Fender",
            model="Jaguar",
            year=1962,
            finish="sunburst",
            condition=Condition.EXCELLENT,
            price_usd=22000,
            url="https://shop.a/jag",
            raw_title="1962 Fender Jaguar Sunburst",
        ),
        score=0.91,
        reasoning="brand=100; model=100",
    )


def test_render_digest_includes_listing_data() -> None:
    subject, text, html = render_digest("jag-hunt", QuerySpec(brand="Fender"), [_scored()])
    assert "1 new match" in subject
    assert "Shop A" in text
    assert "1962 Fender Jaguar" in text
    assert "https://shop.a/jag" in text
    assert "Shop A" in html
    assert "shop.a/jag" in html


def test_smtp_sender_raises_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GS_SMTP_HOST", "")
    monkeypatch.setenv("GS_SMTP_USERNAME", "")
    monkeypatch.setenv("GS_SMTP_PASSWORD", "")
    monkeypatch.setenv("GS_NOTIFY_FROM", "")
    from guitar_searcher.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(EmailNotConfigured):
        SmtpSender.from_settings()


def test_send_no_matches_is_noop() -> None:
    # Should not raise even without SMTP config because there's nothing to send.
    send_match_digest("w", QuerySpec(), [])
