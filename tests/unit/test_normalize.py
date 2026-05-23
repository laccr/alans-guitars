from __future__ import annotations

from guitar_searcher.matching.normalize import normalize_title


def test_recognizes_fender_jaguar() -> None:
    n = normalize_title("1962 Fender Jaguar Sunburst - All Original")
    assert n.brand == "Fender"
    assert n.year == 1962
    assert n.year_confidence > 0.8
    assert n.finish == "sunburst"


def test_recognizes_gibson_les_paul() -> None:
    n = normalize_title("Gibson Les Paul Standard 1959 Vintage Burst")
    assert n.brand == "Gibson"
    assert n.year == 1959
    # "vintage burst" isn't in the canonical finish list — it should pick "burst" via "cherry burst" no — actually nothing.
    # Just ensure brand+year are populated.


def test_decade_only_low_confidence() -> None:
    n = normalize_title("Vintage 1960s Fender Stratocaster")
    assert n.brand == "Fender"
    assert n.year == 1960
    assert n.year_confidence < 0.5


def test_unknown_brand_returns_none() -> None:
    n = normalize_title("Some random handcrafted guitar 2019")
    assert n.brand is None
    assert n.year == 2019


def test_finish_extraction() -> None:
    n = normalize_title("Fender Strat in Candy Apple Red")
    assert n.finish == "candy apple red"
