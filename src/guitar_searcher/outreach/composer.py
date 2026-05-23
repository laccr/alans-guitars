"""Compose an initial inquiry email asking a shop if they have a specific guitar."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from html import escape
from typing import Any, cast

from anthropic import Anthropic

from guitar_searcher.llm.client import CLAUDE_MODEL, get_anthropic_client
from guitar_searcher.outreach.compliance import (
    CanSpamConfig,
    ensure_can_spam_ready,
    footer_html,
    footer_text,
)
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.schemas.shop import Shop
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class ComposedMessage:
    subject: str
    text_body: str
    html_body: str
    message_id: str
    to_addr: str


_USER_NAME = "Brent Scott"  # from memory: user-name


def _default_hook(shop: Shop, query: QuerySpec) -> str:
    if shop.classification.value == "vintage_specialist":
        return (
            f"Your reputation for vintage instruments led me to reach out — I'm hunting for a "
            f"{query.display()}."
        )
    if shop.classification.value == "boutique":
        return f"I'm searching for a specific instrument — a {query.display()} — and your shop came up."
    return f"I'm looking for a {query.display()} and wanted to ask if it's something you'd come across."


_LLM_SYSTEM = (
    "You write very short opening sentences for an email inquiry from a guitar collector to a "
    "guitar shop. The collector is asking whether the shop has, or could find, a specific guitar. "
    "Tone: warm, polite, knowledgeable, not effusive. One sentence, no exclamation points, no "
    "emoji, never make up facts about the shop. If you don't know much about the shop, write a "
    "neutral opener."
)


def _llm_hook(client: Anthropic, shop: Shop, query: QuerySpec) -> str | None:
    """Try to get a personalized opener from Claude. Return None on any failure."""
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=120,
            system=cast(
                Any,
                [
                    {
                        "type": "text",
                        "text": _LLM_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            ),
            messages=cast(
                Any,
                [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "shop_name": shop.name,
                                "shop_classification": shop.classification.value,
                                "shop_city": shop.city,
                                "shop_state": shop.state,
                                "shop_notes": shop.notes,
                                "guitar_being_sought": query.display(),
                            },
                            default=str,
                        ),
                    }
                ],
            ),
        )
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "").strip()
                if text:
                    return text
    except Exception as exc:
        log.warning("composer.llm_hook_failed", error=str(exc))
    return None


def _build_body(
    *,
    shop: Shop,
    query: QuerySpec,
    hook: str,
    cfg: CanSpamConfig,
) -> tuple[str, str]:
    """Return (text_body, html_body) WITHOUT the footer (added by caller)."""
    greeting = f"Hi {shop.name} team,"
    ask_lines = [
        f"My name is {_USER_NAME} and I'm looking for the following guitar:",
        "",
        f"    {query.display()}",
        "",
    ]
    if query.max_price_usd:
        ask_lines.append(f"Budget: up to ${query.max_price_usd:,.0f}.")
    if query.all_original_only:
        ask_lines.append("I'm looking for an all-original example (no refins, partscasters, or reissues).")
    closing = (
        "If you happen to have one, or know of one, I'd love to hear about it — please reply with "
        "what you know, including condition and asking price if applicable. Even a 'no, but try X' "
        "is genuinely helpful."
    )

    text_body = "\n".join(
        [
            greeting,
            "",
            hook,
            "",
            *ask_lines,
            "",
            closing,
            "",
            "Thanks for your time,",
            _USER_NAME,
        ]
    )

    html_paragraphs = [
        f"<p>{escape(greeting)}</p>",
        f"<p>{escape(hook)}</p>",
        f"<p>My name is {escape(_USER_NAME)} and I'm looking for the following guitar:</p>",
        f"<blockquote style='border-left:3px solid #ccc;padding-left:8px'>{escape(query.display())}</blockquote>",
    ]
    if query.max_price_usd:
        html_paragraphs.append(f"<p>Budget: up to <strong>${query.max_price_usd:,.0f}</strong>.</p>")
    if query.all_original_only:
        html_paragraphs.append(
            "<p>I'm looking for an all-original example (no refins, partscasters, or reissues).</p>"
        )
    html_paragraphs.extend(
        [
            f"<p>{escape(closing)}</p>",
            f"<p>Thanks for your time,<br>{escape(_USER_NAME)}</p>",
        ]
    )
    html_body = "<html><body style='font-family:-apple-system,Segoe UI,sans-serif;max-width:600px'>" + "".join(html_paragraphs) + "</body></html>"
    return text_body, html_body


def compose_initial_inquiry(
    *,
    shop: Shop,
    query: QuerySpec,
    use_llm_personalization: bool = True,
) -> ComposedMessage:
    """Render a personalized initial inquiry. Enforces CAN-SPAM presence up front."""
    if not shop.email:
        raise ValueError(f"Shop {shop.name!r} has no email address")
    cfg = ensure_can_spam_ready()

    hook = _default_hook(shop, query)
    if use_llm_personalization:
        client = get_anthropic_client()
        if client is not None:
            llm = _llm_hook(client, shop, query)
            if llm:
                hook = llm

    text_body, html_body = _build_body(shop=shop, query=query, hook=hook, cfg=cfg)
    text_body += footer_text(cfg)
    html_body = html_body.replace("</body>", footer_html(cfg) + "</body>")

    subject = f"Inquiring about a {query.display()}"
    message_id = f"<{uuid.uuid4()}@guitar-searcher>"

    return ComposedMessage(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        message_id=message_id,
        to_addr=shop.email,
    )
