from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from guitar_searcher.schemas import NormalizedListing, QuerySpec

_ORIGINALITY_NEGATIVES: tuple[str, ...] = (
    "refin",
    "refinish",
    "refinished",
    "partscaster",
    "parts caster",
    "parts-caster",
    "replaced pickups",
    "non-original",
    "non original",
    "frankenstein",
    "rebuilt",
    "reissue",
    "ri ",
)


@dataclass
class ScoredListing:
    listing: NormalizedListing
    score: float
    reasoning: str
    disqualified: bool = False


def _haystack(listing: NormalizedListing) -> str:
    parts = [
        listing.raw_title or "",
        listing.raw_description or "",
        listing.brand or "",
        listing.model or "",
        listing.finish or "",
    ]
    return " ".join(parts).lower()


def score_listing(query: QuerySpec, listing: NormalizedListing) -> ScoredListing:
    """Score a listing 0..1 against the query. Apply hard-gate disqualifications first."""
    text = _haystack(listing)
    notes: list[str] = []
    score = 0.0
    weight_total = 0.0

    # ─── Hard gates ────────────────────────────────────────────────────────
    if (
        query.max_price_usd is not None
        and listing.price_usd is not None
        and listing.price_usd > query.max_price_usd
    ):
        return ScoredListing(
            listing=listing,
            score=0.0,
            reasoning=f"price ${listing.price_usd:,.0f} exceeds max ${query.max_price_usd:,.0f}",
            disqualified=True,
        )

    if (
        query.min_price_usd is not None
        and listing.price_usd is not None
        and listing.price_usd < query.min_price_usd
    ):
        return ScoredListing(
            listing=listing,
            score=0.0,
            reasoning=f"price ${listing.price_usd:,.0f} below min ${query.min_price_usd:,.0f}",
            disqualified=True,
        )

    if query.exclude:
        for ex in query.exclude:
            if ex.lower() in text:
                return ScoredListing(
                    listing=listing,
                    score=0.0,
                    reasoning=f"excluded keyword {ex!r} present",
                    disqualified=True,
                )

    if query.must_have:
        missing = [m for m in query.must_have if m.lower() not in text]
        if missing:
            return ScoredListing(
                listing=listing,
                score=0.0,
                reasoning=f"missing required keywords: {', '.join(missing)}",
                disqualified=True,
            )

    if query.all_original_only:
        hit = next((neg for neg in _ORIGINALITY_NEGATIVES if neg in text), None)
        if hit:
            return ScoredListing(
                listing=listing,
                score=0.0,
                reasoning=f"all-original required but listing mentions {hit!r}",
                disqualified=True,
            )

    if query.year_min is not None and listing.year is not None and listing.year < query.year_min:
        # Soft penalty when year_confidence is low, hard gate when high.
        if listing.year_confidence >= 0.7:
            return ScoredListing(
                listing=listing,
                score=0.0,
                reasoning=f"year {listing.year} below min {query.year_min}",
                disqualified=True,
            )
        notes.append(f"year {listing.year} below min but low-confidence")
    if query.year_max is not None and listing.year is not None and listing.year > query.year_max:
        if listing.year_confidence >= 0.7:
            return ScoredListing(
                listing=listing,
                score=0.0,
                reasoning=f"year {listing.year} above max {query.year_max}",
                disqualified=True,
            )
        notes.append(f"year {listing.year} above max but low-confidence")

    if query.conditions and listing.condition.value not in {c.lower() for c in query.conditions}:
        # Don't disqualify outright — many sources don't populate condition reliably.
        notes.append(f"condition {listing.condition.value} not in {query.conditions}")
        score -= 0.05

    # ─── Soft scoring ──────────────────────────────────────────────────────
    if query.brand:
        b_score = (
            fuzz.WRatio(query.brand, listing.brand or "") if listing.brand else fuzz.partial_ratio(
                query.brand, text
            )
        )
        score += (b_score / 100.0) * 0.30
        weight_total += 0.30
        notes.append(f"brand={b_score:.0f}")

    if query.model:
        m_score = (
            fuzz.WRatio(query.model, listing.model or "") if listing.model else fuzz.partial_ratio(
                query.model, text
            )
        )
        score += (m_score / 100.0) * 0.35
        weight_total += 0.35
        notes.append(f"model={m_score:.0f}")

    if query.finish:
        f_score = (
            fuzz.partial_ratio(query.finish.lower(), (listing.finish or "").lower())
            if listing.finish
            else fuzz.partial_ratio(query.finish.lower(), text)
        )
        score += (f_score / 100.0) * 0.15
        weight_total += 0.15
        notes.append(f"finish={f_score:.0f}")

    if query.year_min is not None or query.year_max is not None:
        y_score = 0.0
        if listing.year is not None:
            in_range = True
            if query.year_min is not None and listing.year < query.year_min:
                in_range = False
            if query.year_max is not None and listing.year > query.year_max:
                in_range = False
            y_score = (1.0 if in_range else 0.3) * listing.year_confidence
        score += y_score * 0.20
        weight_total += 0.20
        notes.append(f"year={y_score:.2f}")

    if query.keywords:
        hits = sum(1 for kw in query.keywords if kw.lower() in text)
        if hits:
            score += min(0.10, 0.03 * hits)
            notes.append(f"keywords={hits}/{len(query.keywords)}")

    score = score / max(weight_total, 0.01) if weight_total > 0 else 0.5
    score = max(0.0, min(1.0, score))
    return ScoredListing(
        listing=listing,
        score=round(score, 4),
        reasoning="; ".join(notes) or "no criteria",
        disqualified=False,
    )
