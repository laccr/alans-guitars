"""Orchestrates a single search across all enabled scrapers and persists results."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

import anyio
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from guitar_searcher.config import get_settings
from guitar_searcher.db.seed import row_to_shop
from guitar_searcher.matching.fingerprint import fingerprint_listing
from guitar_searcher.matching.llm_tiebreaker import llm_tiebreak
from guitar_searcher.matching.score import ScoredListing, score_listing
from guitar_searcher.models.listing import ListingRow, MatchRow, SearchRow, SearchRunRow
from guitar_searcher.models.shop import ShopRow
from guitar_searcher.schemas import (
    InventoryStrategy,
    ListingSource,
    NormalizedListing,
    QuerySpec,
    Shop,
)
from guitar_searcher.scrapers import enabled_scrapers
from guitar_searcher.scrapers.base import ScraperContext, ScraperResult
from guitar_searcher.utils.logging import get_logger
from guitar_searcher.utils.ratelimit import HostRateLimiter

_Coro = Coroutine[Any, Any, ScraperResult]

log = get_logger(__name__)


async def run_search(
    session: Session,
    query: QuerySpec,
    *,
    save: bool = True,
    use_llm_tiebreaker: bool = True,
    min_score: float = 0.35,
) -> tuple[SearchRunRow | None, list[ScoredListing]]:
    """Execute the query across all enabled scrapers; return persisted run + ranked hits."""
    settings = get_settings()
    log.info("search.start", query=query.display())

    shops = _load_active_shops(session)
    search_run = _create_search_run(session, query) if save else None

    started_at = datetime.now(UTC)
    rate_limiter = HostRateLimiter(rps=settings.per_host_rps)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": settings.user_agent},
        http2=True,
        limits=httpx.Limits(max_connections=settings.max_concurrency * 2),
    ) as client:
        ctx = ScraperContext(
            client=client,
            rate_limiter=rate_limiter,
            user_agent=settings.user_agent,
            timeout_s=30.0,
        )
        tasks = _plan_scraper_tasks(query, ctx, shops)
        results = await _run_with_concurrency(tasks, settings.max_concurrency)

    all_listings: list[NormalizedListing] = []
    examined_total = 0
    for r in results:
        if r.error:
            log.warning("scraper.error", scraper=r.scraper_name, error=r.error)
        examined_total += r.examined
        all_listings.extend(r.listings)

    log.info("search.scraped", listings=len(all_listings), examined=examined_total)

    deduped = _dedupe(all_listings)
    log.info("search.deduped", before=len(all_listings), after=len(deduped))

    scored = [score_listing(query, listing) for listing in deduped]
    scored = [s for s in scored if not s.disqualified and s.score >= min_score]

    if use_llm_tiebreaker:
        scored = llm_tiebreak(query, scored)

    scored.sort(key=lambda s: s.score, reverse=True)

    if save and search_run is not None:
        finished_at = datetime.now(UTC)
        _persist_results(session, search_run, scored, shops_queried=len(shops), examined=examined_total)
        search_run.started_at = started_at
        search_run.finished_at = finished_at
        search_run.matches_found = len(scored)
        search_run.status = "complete"
        session.commit()

    return search_run, scored


def _load_active_shops(session: Session) -> list[Shop]:
    rows = (
        session.execute(select(ShopRow).where(ShopRow.active.is_(True)))
        .scalars()
        .all()
    )
    return [row_to_shop(r) for r in rows]


def _create_search_run(session: Session, query: QuerySpec) -> SearchRunRow:
    search = SearchRow(query_spec_json=query.model_dump(mode="json"), is_watch=False)
    session.add(search)
    session.flush()
    run = SearchRunRow(
        search_id=search.id,
        started_at=datetime.now(UTC),
        status="running",
    )
    session.add(run)
    session.flush()
    return run


def _plan_scraper_tasks(
    query: QuerySpec, ctx: ScraperContext, shops: list[Shop]
) -> list[tuple[str, _Coro]]:
    """Return list of (label, coroutine) tasks across generic and shop-bound scrapers."""
    tasks: list[tuple[str, _Coro]] = []
    registry = enabled_scrapers()

    # Tier A — generic scrapers fire once
    for name, cls in registry.items():
        scraper = cls()
        if scraper.is_generic:
            tasks.append((name, scraper.search(query, ctx, shop=None)))

    # Tier B — shop-bound scrapers fire once per matching shop
    for shop in shops:
        strategy = shop.inventory_strategy
        if strategy == InventoryStrategy.SHOPIFY_JSON:
            scraper_cls = registry.get("shopify_generic")
            if scraper_cls:
                tasks.append((f"shopify_generic:{shop.domain}", scraper_cls().search(query, ctx, shop)))
        elif strategy == InventoryStrategy.DEDICATED_SCRAPER and shop.scraper_module:
            scraper_cls = registry.get(shop.scraper_module)
            if scraper_cls and not scraper_cls.is_generic:
                tasks.append((f"{shop.scraper_module}:{shop.domain}", scraper_cls().search(query, ctx, shop)))
        # REVERB_API shops are already covered by the generic reverb_api scraper.
    return tasks


async def _run_with_concurrency(
    tasks: list[tuple[str, _Coro]], concurrency: int
) -> list[ScraperResult]:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[ScraperResult] = []

    async def _wrap(label: str, coro: _Coro) -> None:
        async with semaphore:
            try:
                result = await coro
                results.append(result)
            except Exception as exc:
                log.warning("scraper.crash", label=label, error=str(exc))
                results.append(ScraperResult(scraper_name=label, error=str(exc)))

    async with anyio.create_task_group() as tg:
        for label, coro in tasks:
            tg.start_soon(_wrap, label, coro)
    return results


def _dedupe(listings: list[NormalizedListing]) -> list[NormalizedListing]:
    by_fp: dict[str, NormalizedListing] = {}
    for listing in listings:
        fp = listing.fingerprint or fingerprint_listing(listing)
        listing.fingerprint = fp
        existing = by_fp.get(fp)
        if existing is None:
            by_fp[fp] = listing
            continue
        if (
            existing.source == ListingSource.REVERB_API
            and listing.source != ListingSource.REVERB_API
        ):
            by_fp[fp] = listing
    return list(by_fp.values())


def _persist_results(
    session: Session,
    run: SearchRunRow,
    scored: list[ScoredListing],
    *,
    shops_queried: int,
    examined: int,
) -> None:
    run.shops_queried = shops_queried
    run.listings_examined = examined

    shops_by_domain = {
        domain: shop_id
        for shop_id, domain in session.execute(select(ShopRow.id, ShopRow.domain)).all()
    }

    for rank, s in enumerate(scored, start=1):
        listing_row = _upsert_listing(session, s.listing, shops_by_domain)
        session.add(
            MatchRow(
                search_run_id=run.id,
                listing_id=listing_row.id,
                score=s.score,
                rank=rank,
                reasoning=s.reasoning,
            )
        )


def _upsert_listing(
    session: Session, listing: NormalizedListing, shops_by_domain: dict[str, int]
) -> ListingRow:
    existing = session.execute(
        select(ListingRow).where(
            ListingRow.source == listing.source.value,
            ListingRow.source_listing_id == listing.source_listing_id,
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    shop_id = shops_by_domain.get(listing.shop_domain or "")

    if existing is None:
        row = ListingRow(
            source=listing.source.value,
            source_listing_id=listing.source_listing_id,
            shop_id=shop_id,
            brand=listing.brand,
            model=listing.model,
            year=listing.year,
            year_confidence=listing.year_confidence,
            finish=listing.finish,
            color=listing.color,
            condition=listing.condition.value,
            price_usd=listing.price_usd,
            currency=listing.currency,
            url=str(listing.url),
            image_urls=[str(u) for u in listing.image_urls],
            raw_title=listing.raw_title,
            raw_description=listing.raw_description,
            serial_number=listing.serial_number,
            seen_at=listing.seen_at,
            last_seen_at=now,
            fingerprint=listing.fingerprint,
        )
        session.add(row)
        session.flush()
        return row
    existing.last_seen_at = now
    existing.price_usd = listing.price_usd
    existing.fingerprint = listing.fingerprint
    return existing
