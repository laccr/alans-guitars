"""OpenStreetMap Overpass discovery — `shop=musical_instruments` in the US.

OSM is volunteer-maintained, so coverage is patchy but real and free. Use it to seed
candidate shops that aren't on Reverb. New shops land with `inventory_strategy=email_only`
(Phase 3 outreach candidates) — manual classification can refine later.

Be polite: Overpass is a free public service. We make exactly one US-wide query per run
and cache locally. Don't loop this in a cron job — quarterly refresh is plenty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from guitar_searcher.config import get_settings
from guitar_searcher.schemas.shop import InventoryStrategy, Shop, ShopClassification
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

_QUERY = """
[out:json][timeout:120];
area["ISO3166-1"="US"][admin_level=2]->.us;
(
  node["shop"="musical_instruments"](area.us);
  way["shop"="musical_instruments"](area.us);
  relation["shop"="musical_instruments"](area.us);
);
out center tags;
"""


@dataclass
class OsmDiscoveryResult:
    raw_elements: int = 0
    candidates: list[Shop] = field(default_factory=list)


async def discover_osm_shops(*, timeout_s: float = 180.0) -> OsmDiscoveryResult:
    """One Overpass query for all US musical-instruments shops."""
    settings = get_settings()
    headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}
    result = OsmDiscoveryResult()

    log.info("osm.querying", url=_OVERPASS_URL)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s), headers=headers) as client:
        try:
            resp = await client.post(_OVERPASS_URL, data={"data": _QUERY})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("osm.failed", error=str(exc))
            raise

    payload: dict[str, Any] = resp.json()
    elements = payload.get("elements", [])
    result.raw_elements = len(elements)
    log.info("osm.received", elements=result.raw_elements)

    for el in elements:
        shop = _shop_from_osm(el)
        if shop is not None:
            result.candidates.append(shop)
    return result


def _shop_from_osm(element: dict[str, Any]) -> Shop | None:
    tags = element.get("tags") or {}
    name = tags.get("name")
    if not name:
        return None

    website = (tags.get("website") or tags.get("contact:website") or "").strip()
    phone = tags.get("phone") or tags.get("contact:phone")
    email = tags.get("email") or tags.get("contact:email")

    city = tags.get("addr:city")
    state = tags.get("addr:state")
    street_bits = [tags.get("addr:housenumber"), tags.get("addr:street")]
    street = " ".join(b for b in street_bits if b) or None
    postal = tags.get("addr:postcode")

    if website:
        domain = _domain_of(website) or f"osm.{element.get('type', 'n')}.{element.get('id')}"
        url = website if "://" in website else f"https://{website}"
    else:
        domain = f"osm.{element.get('type','n')}.{element.get('id')}"
        url = f"https://www.openstreetmap.org/{element.get('type','node')}/{element.get('id')}"

    return Shop(
        name=name,
        domain=domain,
        website_url=url,
        email=email,
        phone=phone,
        street=street,
        city=city,
        state=state,
        postal_code=postal,
        timezone=None,
        classification=ShopClassification.UNKNOWN,
        inventory_strategy=InventoryStrategy.EMAIL_ONLY,
        scraper_module=None,
        notes=None,
        active=False,  # discovered shops require manual activation
        discovered_from="osm",
        last_verified_at=datetime.now(UTC),
    )


def _domain_of(url: str) -> str | None:
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None
