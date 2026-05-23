from __future__ import annotations

from guitar_searcher.matching.score import score_listing
from guitar_searcher.schemas import Condition, ListingSource, NormalizedListing, QuerySpec


def _listing(**kw: object) -> NormalizedListing:
    defaults = dict(
        source=ListingSource.SHOP_DIRECT,
        source_listing_id="x",
        shop_name="Shop",
        brand="Fender",
        model="Jaguar",
        year=1962,
        finish="sunburst",
        condition=Condition.EXCELLENT,
        price_usd=22000,
        url="https://example.com/1",
        raw_title="1962 Fender Jaguar Sunburst",
    )
    defaults.update(kw)
    return NormalizedListing(**defaults)  # type: ignore[arg-type]


def test_perfect_match_scores_high() -> None:
    q = QuerySpec(brand="Fender", model="Jaguar", year_min=1960, year_max=1965, finish="sunburst", max_price_usd=25000)
    s = score_listing(q, _listing())
    assert not s.disqualified
    assert s.score > 0.85


def test_over_budget_disqualifies() -> None:
    q = QuerySpec(brand="Fender", model="Jaguar", max_price_usd=10000)
    s = score_listing(q, _listing(price_usd=22000))
    assert s.disqualified
    assert s.score == 0


def test_excluded_keyword_disqualifies() -> None:
    q = QuerySpec(brand="Fender", model="Jaguar", exclude=["partscaster"])
    s = score_listing(q, _listing(raw_title="Fender Jaguar partscaster project"))
    assert s.disqualified


def test_year_out_of_range_high_conf_disqualifies() -> None:
    q = QuerySpec(brand="Fender", model="Jaguar", year_min=1960, year_max=1965)
    s = score_listing(q, _listing(year=1985, year_confidence=1.0))
    assert s.disqualified


def test_year_out_of_range_low_conf_keeps() -> None:
    q = QuerySpec(brand="Fender", model="Jaguar", year_min=1960, year_max=1965)
    s = score_listing(q, _listing(year=1985, year_confidence=0.3))
    assert not s.disqualified


def test_all_original_rejects_refin() -> None:
    q = QuerySpec(brand="Fender", model="Jaguar", all_original_only=True)
    s = score_listing(q, _listing(raw_title="Fender Jaguar 1962 — Refin Sunburst"))
    assert s.disqualified


def test_empty_query_gives_neutral() -> None:
    s = score_listing(QuerySpec(), _listing())
    assert not s.disqualified
    assert 0.4 < s.score < 0.6
