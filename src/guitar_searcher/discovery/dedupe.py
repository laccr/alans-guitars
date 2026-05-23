"""Fuzzy shop deduplication.

When discovering shops from a new source, we want to merge into existing rows when
they're plausibly the same shop, not create duplicates. Strategy:

1. Domain exact match wins outright.
2. Reverb-slug exact match wins outright.
3. Otherwise: same city/state AND fuzzy-name similarity > 88 (rapidfuzz WRatio).
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from guitar_searcher.models.shop import ShopRow
from guitar_searcher.schemas.shop import Shop

NAME_SIM_THRESHOLD = 88


def _norm_domain(value: str | None) -> str | None:
    if not value:
        return None
    value = value.lower().strip()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    return value.split("/")[0] or None


def find_existing_shop(session: Session, candidate: Shop) -> ShopRow | None:
    """Return the row this candidate likely refers to, or None for net-new."""
    cand_domain = _norm_domain(candidate.domain)
    if cand_domain:
        row = session.execute(
            select(ShopRow).where(ShopRow.domain == cand_domain)
        ).scalar_one_or_none()
        if row is not None:
            return row

    if candidate.reverb_shop_slug:
        row = session.execute(
            select(ShopRow).where(ShopRow.reverb_shop_slug == candidate.reverb_shop_slug)
        ).scalar_one_or_none()
        if row is not None:
            return row

    if candidate.city and candidate.state:
        cohort = session.execute(
            select(ShopRow).where(
                ShopRow.city == candidate.city,
                ShopRow.state == candidate.state,
            )
        ).scalars().all()
        for row in cohort:
            sim = fuzz.WRatio(candidate.name, row.name)
            if sim >= NAME_SIM_THRESHOLD:
                return row
    return None


def merge_into(row: ShopRow, candidate: Shop) -> None:
    """Fill in null/missing fields on row from candidate; never overwrite a populated field
    except to add a previously-unknown reverb_shop_slug.
    """
    if not row.email and candidate.email:
        row.email = candidate.email
    if not row.phone and candidate.phone:
        row.phone = candidate.phone
    if not row.street and candidate.street:
        row.street = candidate.street
    if not row.city and candidate.city:
        row.city = candidate.city
    if not row.state and candidate.state:
        row.state = candidate.state
    if not row.postal_code and candidate.postal_code:
        row.postal_code = candidate.postal_code
    if not row.timezone and candidate.timezone:
        row.timezone = candidate.timezone
    if not row.reverb_shop_slug and candidate.reverb_shop_slug:
        row.reverb_shop_slug = candidate.reverb_shop_slug
    if candidate.last_verified_at:
        row.last_verified_at = candidate.last_verified_at
