from __future__ import annotations

from guitar_searcher.db.seed import load_seed_shops, upsert_shops
from guitar_searcher.db.session import get_session
from guitar_searcher.schemas.shop import InventoryStrategy


def test_seed_yaml_loads_cleanly() -> None:
    shops = load_seed_shops()
    assert len(shops) >= 20
    by_strategy: dict[str, int] = {}
    for s in shops:
        by_strategy[s.inventory_strategy.value] = by_strategy.get(s.inventory_strategy.value, 0) + 1
    # Sanity: we should have multiple strategies represented.
    assert by_strategy.get(InventoryStrategy.SHOPIFY_JSON.value, 0) >= 5
    assert by_strategy.get(InventoryStrategy.DEDICATED_SCRAPER.value, 0) >= 4
    assert by_strategy.get(InventoryStrategy.REVERB_API.value, 0) >= 2


def test_seed_upsert_idempotent(tmp_db: str) -> None:
    shops = load_seed_shops()
    with get_session() as s:
        inserted, updated = upsert_shops(s, shops)
        assert inserted == len(shops)
        assert updated == 0
    with get_session() as s:
        inserted2, updated2 = upsert_shops(s, shops)
        assert inserted2 == 0
        assert updated2 == len(shops)
