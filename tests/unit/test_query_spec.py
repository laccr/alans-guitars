from __future__ import annotations

import pytest

from guitar_searcher.schemas import QuerySpec


def test_valid_query() -> None:
    q = QuerySpec(brand="Fender", model="Jaguar", year_min=1962, year_max=1965, max_price_usd=25000)
    assert q.display().startswith("Fender Jaguar 1962-1965")


def test_year_inversion_rejected() -> None:
    with pytest.raises(ValueError):
        QuerySpec(year_min=1990, year_max=1960)


def test_price_inversion_rejected() -> None:
    with pytest.raises(ValueError):
        QuerySpec(min_price_usd=5000, max_price_usd=1000)


def test_default_display() -> None:
    assert QuerySpec().display() == "(any guitar)"
