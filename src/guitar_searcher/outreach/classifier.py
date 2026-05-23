"""Classify outreach replies into a small set of buckets via Claude.

Categories:
  has_it       — the shop has (or claims to have) the guitar
  knows_of     — the shop knows of one elsewhere or will look
  no           — shop says they don't have it and can't help
  unclear      — shop replied but the answer is ambiguous
  autoresponder — out-of-office / vacation autoresponder; ignore for follow-up
  unsubscribe  — shop wants no further contact; record opt-out
"""
from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from guitar_searcher.llm.client import CLAUDE_MODEL, get_anthropic_client
from guitar_searcher.models.outreach import OutreachAttemptRow, OutreachReplyRow
from guitar_searcher.outreach.compliance import looks_like_unsubscribe, strip_quoted_reply
from guitar_searcher.outreach.queue import record_opt_out
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)

CLASSIFICATIONS: tuple[str, ...] = (
    "has_it",
    "knows_of",
    "no",
    "unclear",
    "autoresponder",
    "unsubscribe",
)

_SYSTEM = """You classify replies to guitar inquiries. The user emailed a guitar shop asking
if they have a specific guitar. You see only the shop's reply.

Pick exactly one of: has_it | knows_of | no | unclear | autoresponder | unsubscribe.

Rules:
- "has_it": the shop says they have, may have, or are bringing in the specific guitar.
- "knows_of": shop knows someone else who has one, or will search for one for the buyer.
- "no": shop clearly says no and doesn't help further.
- "unclear": you can't tell from the message.
- "autoresponder": clearly an out-of-office / auto-reply.
- "unsubscribe": shop asks to be removed from any further outreach. Anything indicating
  they don't want to hear from us again falls here.

Also extract listing details if has_it: brand, model, year, finish, price (USD), condition.
"""

_TOOL: dict[str, Any] = {
    "name": "classify_reply",
    "description": "Return a classification and optional extracted listing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classification": {"type": "string", "enum": list(CLASSIFICATIONS)},
            "rationale": {"type": "string"},
            "follow_up_needed": {"type": "boolean"},
            "extracted_listings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "brand": {"type": "string"},
                        "model": {"type": "string"},
                        "year": {"type": "integer"},
                        "finish": {"type": "string"},
                        "price_usd": {"type": "number"},
                        "condition": {"type": "string"},
                    },
                },
            },
        },
        "required": ["classification", "rationale", "follow_up_needed"],
    },
}


def classify_reply(body: str) -> dict[str, Any]:
    """Classify one reply body. Strips quoted prior conversation before any analysis."""
    new_content = strip_quoted_reply(body) or body
    if looks_like_unsubscribe(new_content):
        return {
            "classification": "unsubscribe",
            "rationale": "Body contains opt-out language (heuristic match).",
            "follow_up_needed": False,
            "extracted_listings": [],
        }

    client = get_anthropic_client()
    if client is None:
        return {
            "classification": "unclear",
            "rationale": "LLM unavailable; manual review required.",
            "follow_up_needed": True,
            "extracted_listings": [],
        }

    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=cast(
                Any,
                [
                    {
                        "type": "text",
                        "text": _SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            ),
            tools=cast(Any, [_TOOL]),
            tool_choice=cast(Any, {"type": "tool", "name": "classify_reply"}),
            messages=cast(
                Any,
                [{"role": "user", "content": new_content[:6000]}],
            ),
        )
    except Exception as exc:
        log.warning("classifier.llm_failed", error=str(exc))
        return {
            "classification": "unclear",
            "rationale": f"LLM call failed: {exc}",
            "follow_up_needed": True,
            "extracted_listings": [],
        }

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            payload = cast(dict[str, Any], getattr(block, "input", {}) or {})
            cls = payload.get("classification", "unclear")
            if cls not in CLASSIFICATIONS:
                cls = "unclear"
            return {
                "classification": cls,
                "rationale": payload.get("rationale", ""),
                "follow_up_needed": bool(payload.get("follow_up_needed", False)),
                "extracted_listings": payload.get("extracted_listings", []) or [],
            }
    return {
        "classification": "unclear",
        "rationale": "No structured output from LLM.",
        "follow_up_needed": True,
        "extracted_listings": [],
    }


def classify_pending(session: Session, *, limit: int = 20) -> int:
    """Classify outreach_replies still marked 'unclear'. Returns number classified."""
    rows = (
        session.execute(
            select(OutreachReplyRow)
            .where(OutreachReplyRow.classification == "unclear")
            .limit(limit)
        )
        .scalars()
        .all()
    )
    n = 0
    for reply in rows:
        result = classify_reply(reply.raw_body)
        reply.classification = result["classification"]
        reply.follow_up_needed = result["follow_up_needed"]
        if result["extracted_listings"]:
            reply.extracted_listings_json = result["extracted_listings"]
        if reply.classification == "unsubscribe":
            attempt = session.get(OutreachAttemptRow, reply.attempt_id)
            if attempt is not None:
                record_opt_out(
                    session,
                    attempt.shop_id,
                    source="reply",
                    note=result["rationale"],
                )
        n += 1
    session.commit()
    return n
