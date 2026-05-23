from __future__ import annotations

import json
from typing import Any, cast

from guitar_searcher.llm.client import CLAUDE_MODEL, get_anthropic_client
from guitar_searcher.matching.score import ScoredListing
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)

_TIEBREAK_SYSTEM = """You are a vintage guitar expert helping rank guitar listings against a buyer's query.

For each listing, judge whether it matches the buyer's criteria. Be skeptical of titles that mention reissues, refins, or partscasters when the buyer wants something original. Give each listing a confidence from 0.0 to 1.0 and a one-sentence rationale.

Always return JSON in the exact schema requested by the tool."""

_TOOL_SCHEMA: dict[str, Any] = {
    "name": "rank_listings",
    "description": "Return per-listing match confidence and rationale.",
    "input_schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "rationale": {"type": "string"},
                    },
                    "required": ["id", "confidence", "rationale"],
                },
            }
        },
        "required": ["results"],
    },
}


def llm_tiebreak(
    query: QuerySpec,
    scored: list[ScoredListing],
    *,
    band_low: float = 0.45,
    band_high: float = 0.75,
) -> list[ScoredListing]:
    """Re-score listings in the ambiguous middle band via the LLM.

    Listings with scores < band_low or > band_high are returned untouched.
    Falls back to the original scores if no API key is configured.
    """
    client = get_anthropic_client()
    if client is None:
        return scored

    ambiguous = [s for s in scored if band_low <= s.score <= band_high]
    if not ambiguous:
        return scored

    user_payload = {
        "query": query.model_dump(exclude_none=True),
        "listings": [
            {
                "id": str(i),
                "title": s.listing.raw_title,
                "brand": s.listing.brand,
                "model": s.listing.model,
                "year": s.listing.year,
                "finish": s.listing.finish,
                "price_usd": s.listing.price_usd,
                "url": str(s.listing.url),
                "current_score": s.score,
                "scoring_notes": s.reasoning,
            }
            for i, s in enumerate(ambiguous)
        ],
    }

    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=cast(
                Any,
                [
                    {
                        "type": "text",
                        "text": _TIEBREAK_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            ),
            tools=cast(Any, [_TOOL_SCHEMA]),
            tool_choice=cast(Any, {"type": "tool", "name": "rank_listings"}),
            messages=cast(
                Any,
                [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(user_payload, default=str),
                            }
                        ],
                    }
                ],
            ),
        )
    except Exception as exc:
        log.warning("llm_tiebreak.failed", error=str(exc))
        return scored

    by_id: dict[str, dict[str, Any]] = {}
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            payload = cast(dict[str, Any], getattr(block, "input", {}) or {})
            for entry in payload.get("results", []):
                by_id[str(entry["id"])] = entry

    out: list[ScoredListing] = []
    for s in scored:
        if band_low <= s.score <= band_high:
            idx = str(ambiguous.index(s))
            ranked = by_id.get(idx)
            if ranked:
                blended = 0.5 * s.score + 0.5 * float(ranked["confidence"])
                out.append(
                    ScoredListing(
                        listing=s.listing,
                        score=round(blended, 4),
                        reasoning=f"{s.reasoning}; LLM: {ranked['rationale']}",
                        disqualified=False,
                    )
                )
                continue
        out.append(s)
    return out
