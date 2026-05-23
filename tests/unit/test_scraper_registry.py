from __future__ import annotations

from guitar_searcher.scrapers import enabled_scrapers, get_scraper


def test_registry_loads_all_scrapers() -> None:
    reg = enabled_scrapers()
    # Tier A
    assert "reverb_api" in reg
    # Generic Tier B
    assert "shopify_generic" in reg
    # Hand-written Tier B
    for name in ("sweetwater", "wildwood", "carter_vintage", "elderly"):
        assert name in reg, f"missing scraper: {name}"


def test_get_scraper_by_name() -> None:
    cls = get_scraper("reverb_api")
    assert cls.name == "reverb_api"
    assert cls.is_generic is True
