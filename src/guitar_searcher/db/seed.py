from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from guitar_searcher.config import get_settings
from guitar_searcher.models.shop import ShopRow
from guitar_searcher.schemas.shop import Shop
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)


def load_seed_shops(yaml_path: Path | None = None) -> list[Shop]:
    if yaml_path is None:
        yaml_path = get_settings().seed_data_dir / "major_retailers.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return [Shop.model_validate(row) for row in data.get("shops", [])]


def upsert_shops(session: Session, shops: list[Shop]) -> tuple[int, int]:
    """Insert new shops, update existing ones (matched by domain). Returns (inserted, updated)."""
    inserted = 0
    updated = 0
    for shop in shops:
        existing = session.execute(
            select(ShopRow).where(ShopRow.domain == shop.domain)
        ).scalar_one_or_none()
        if existing is None:
            session.add(_to_row(shop))
            inserted += 1
        else:
            _update_row(existing, shop)
            updated += 1
    return inserted, updated


def _to_row(shop: Shop) -> ShopRow:
    return ShopRow(
        name=shop.name,
        domain=shop.domain,
        website_url=str(shop.website_url),
        reverb_shop_slug=shop.reverb_shop_slug,
        email=shop.email,
        phone=shop.phone,
        street=shop.street,
        city=shop.city,
        state=shop.state,
        postal_code=shop.postal_code,
        timezone=shop.timezone,
        classification=shop.classification.value,
        inventory_strategy=shop.inventory_strategy.value,
        scraper_module=shop.scraper_module,
        notes=shop.notes,
        active=shop.active,
        discovered_from=shop.discovered_from or "hand_curated",
        last_verified_at=shop.last_verified_at,
    )


def _update_row(row: ShopRow, shop: Shop) -> None:
    row.name = shop.name
    row.website_url = str(shop.website_url)
    row.reverb_shop_slug = shop.reverb_shop_slug
    row.email = shop.email
    row.phone = shop.phone
    row.street = shop.street
    row.city = shop.city
    row.state = shop.state
    row.postal_code = shop.postal_code
    row.timezone = shop.timezone
    row.classification = shop.classification.value
    row.inventory_strategy = shop.inventory_strategy.value
    row.scraper_module = shop.scraper_module
    row.notes = shop.notes
    row.active = shop.active
    if shop.discovered_from:
        row.discovered_from = shop.discovered_from
    if shop.last_verified_at:
        row.last_verified_at = shop.last_verified_at


def row_to_shop(row: ShopRow) -> Shop:
    from guitar_searcher.schemas.shop import InventoryStrategy, ShopClassification

    return Shop(
        name=row.name,
        domain=row.domain,
        website_url=row.website_url,
        reverb_shop_slug=row.reverb_shop_slug,
        email=row.email,
        phone=row.phone,
        street=row.street,
        city=row.city,
        state=row.state,
        postal_code=row.postal_code,
        timezone=row.timezone,
        classification=ShopClassification(row.classification),
        inventory_strategy=InventoryStrategy(row.inventory_strategy),
        scraper_module=row.scraper_module,
        notes=row.notes,
        active=row.active,
        discovered_from=row.discovered_from,
        last_verified_at=row.last_verified_at,
    )
