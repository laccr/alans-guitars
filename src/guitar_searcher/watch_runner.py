"""Saved-watch persistence + execution. Runs a search, persists results, and emits
notifications for matches that haven't been seen before for this watch.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from guitar_searcher.matching.fingerprint import fingerprint_listing
from guitar_searcher.matching.score import ScoredListing
from guitar_searcher.models.listing import SearchRow
from guitar_searcher.models.notifications import NotifiedListingRow
from guitar_searcher.notifications.email_digest import (
    EmailNotConfigured,
    send_match_digest,
)
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.search_runner import run_search
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)


VALID_CADENCES = {"hourly", "daily", "weekly"}


def add_watch(
    session: Session, *, name: str, query: QuerySpec, cadence: str
) -> SearchRow:
    if cadence not in VALID_CADENCES:
        raise ValueError(f"cadence must be one of {sorted(VALID_CADENCES)}; got {cadence!r}")
    row = SearchRow(
        name=name,
        query_spec_json=query.model_dump(mode="json"),
        is_watch=True,
        watch_cadence=cadence,
        watch_active=True,
    )
    session.add(row)
    session.flush()
    return row


def list_watches(session: Session, *, only_active: bool = False) -> list[SearchRow]:
    stmt = select(SearchRow).where(SearchRow.is_watch.is_(True)).order_by(SearchRow.id)
    if only_active:
        stmt = stmt.where(SearchRow.watch_active.is_(True))
    return list(session.execute(stmt).scalars().all())


def set_watch_active(session: Session, search_id: int, active: bool) -> SearchRow:
    row = session.get(SearchRow, search_id)
    if row is None or not row.is_watch:
        raise LookupError(f"No watch with id={search_id}")
    row.watch_active = active
    session.flush()
    return row


def remove_watch(session: Session, search_id: int) -> None:
    row = session.get(SearchRow, search_id)
    if row is None or not row.is_watch:
        raise LookupError(f"No watch with id={search_id}")
    session.delete(row)
    session.flush()


def already_notified_fingerprints(session: Session, search_id: int) -> set[str]:
    rows = session.execute(
        select(NotifiedListingRow.fingerprint).where(
            NotifiedListingRow.search_id == search_id
        )
    ).all()
    return {fp for (fp,) in rows}


def record_notifications(
    session: Session,
    search_id: int,
    matches: Iterable[ScoredListing],
) -> None:
    now = datetime.now(UTC)
    for m in matches:
        fp = m.listing.fingerprint or fingerprint_listing(m.listing)
        session.add(
            NotifiedListingRow(
                search_id=search_id,
                fingerprint=fp,
                listing_url=str(m.listing.url),
                notified_at=now,
            )
        )
    session.flush()


async def run_watch_async(
    session: Session,
    watch: SearchRow,
    *,
    notify: bool = True,
    use_llm_tiebreaker: bool = True,
    min_score: float = 0.35,
) -> tuple[list[ScoredListing], list[ScoredListing]]:
    """Execute one watch. Returns (all_matches, newly_notified_matches)."""
    if not watch.is_watch:
        raise ValueError(f"search {watch.id} is not a watch")

    query = QuerySpec.model_validate(watch.query_spec_json)
    _run, scored = await run_search(
        session,
        query,
        save=True,
        use_llm_tiebreaker=use_llm_tiebreaker,
        min_score=min_score,
    )

    seen = already_notified_fingerprints(session, watch.id)
    new_matches: list[ScoredListing] = []
    for s in scored:
        fp = s.listing.fingerprint or fingerprint_listing(s.listing)
        if fp not in seen:
            new_matches.append(s)

    if notify and new_matches:
        try:
            send_match_digest(watch.name or f"watch-{watch.id}", query, new_matches)
        except EmailNotConfigured as exc:
            log.warning("watch.notify_skipped", watch_id=watch.id, reason=str(exc))
            return scored, []
        record_notifications(session, watch.id, new_matches)
        session.commit()

    return scored, new_matches


def run_watch(session: Session, watch: SearchRow, **kwargs: object) -> tuple[list[ScoredListing], list[ScoredListing]]:
    return asyncio.run(run_watch_async(session, watch, **kwargs))  # type: ignore[arg-type]
