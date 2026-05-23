from __future__ import annotations

from guitar_searcher.db.seed import _to_row
from guitar_searcher.db.session import get_session
from guitar_searcher.discovery.dedupe import find_existing_shop, merge_into
from guitar_searcher.schemas.shop import InventoryStrategy, Shop, ShopClassification


def _shop(**overrides: object) -> Shop:
    defaults = dict(
        name="Test Shop",
        domain="testshop.com",
        website_url="https://testshop.com",
        classification=ShopClassification.BOUTIQUE,
        inventory_strategy=InventoryStrategy.SHOPIFY_JSON,
        active=True,
    )
    defaults.update(overrides)
    return Shop(**defaults)  # type: ignore[arg-type]


def test_domain_exact_match(tmp_db: str) -> None:
    with get_session() as s:
        s.add(_to_row(_shop(name="Test Shop", domain="testshop.com")))
    with get_session() as s:
        found = find_existing_shop(s, _shop(name="A Different Name", domain="testshop.com"))
        assert found is not None
        assert found.name == "Test Shop"


def test_reverb_slug_match(tmp_db: str) -> None:
    with get_session() as s:
        s.add(_to_row(_shop(name="Test", domain="testshop.com", reverb_shop_slug="abc")))
    with get_session() as s:
        found = find_existing_shop(
            s, _shop(name="Other", domain="elsewhere.com", reverb_shop_slug="abc")
        )
        assert found is not None
        assert found.domain == "testshop.com"


def test_fuzzy_city_state_match(tmp_db: str) -> None:
    with get_session() as s:
        s.add(_to_row(_shop(name="Carter Vintage Guitars", domain="carter1.com", city="Nashville", state="TN")))
    with get_session() as s:
        found = find_existing_shop(
            s,
            _shop(
                name="Carter Vintage",
                domain="carter2.com",  # different domain
                city="Nashville",
                state="TN",
            ),
        )
        assert found is not None
        assert found.domain == "carter1.com"


def test_no_match_when_city_differs(tmp_db: str) -> None:
    with get_session() as s:
        s.add(_to_row(_shop(name="Carter Vintage", domain="carter.com", city="Nashville", state="TN")))
    with get_session() as s:
        found = find_existing_shop(
            s,
            _shop(name="Carter Vintage", domain="other.com", city="Houston", state="TX"),
        )
        assert found is None


def test_merge_fills_missing_fields(tmp_db: str) -> None:
    with get_session() as s:
        s.add(_to_row(_shop(name="Test", domain="t.com", phone=None, email=None)))
    with get_session() as s:
        row = find_existing_shop(s, _shop(domain="t.com"))
        assert row is not None
        merge_into(row, _shop(domain="t.com", phone="555-1212", email="hi@t.com"))
    with get_session() as s:
        row = find_existing_shop(s, _shop(domain="t.com"))
        assert row is not None
        assert row.phone == "555-1212"
        assert row.email == "hi@t.com"


def test_merge_does_not_overwrite(tmp_db: str) -> None:
    with get_session() as s:
        s.add(_to_row(_shop(name="Test", domain="t.com", phone="ORIGINAL", email="orig@t.com")))
    with get_session() as s:
        row = find_existing_shop(s, _shop(domain="t.com"))
        assert row is not None
        merge_into(row, _shop(domain="t.com", phone="NEW", email="new@t.com"))
    with get_session() as s:
        row = find_existing_shop(s, _shop(domain="t.com"))
        assert row is not None
        assert row.phone == "ORIGINAL"
        assert row.email == "orig@t.com"
