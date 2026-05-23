"""CAN-SPAM compliance helpers.

CAN-SPAM Act of 2003 applies to any commercial email. Inquiries to retailers about
inventory ARE commercial messages under FTC interpretation. Required elements:

1. Accurate headers (From / Reply-To / Subject not misleading).
2. Honest, descriptive Subject line.
3. Clearly identifies the message as commercial (recommended; not strictly required
   for transactional/relationship messages, but inquiries are borderline so we comply).
4. Includes a valid physical postal address of the sender.
5. Clear, conspicuous, easy way to opt out.
6. Honor opt-out requests within 10 business days; retain opt-out for >= 5 years.

This module enforces (4)-(5) at compose time; (6) is enforced by the queue + classifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

from guitar_searcher.config import get_settings


class MissingComplianceField(RuntimeError):
    """Raised when a required CAN-SPAM field is empty at send time."""


@dataclass(frozen=True)
class CanSpamConfig:
    sender_name: str
    physical_address: str
    reply_to: str

    @classmethod
    def from_settings(cls) -> CanSpamConfig:
        s = get_settings()
        from_addr = s.outreach_from or s.notify_from
        reply_to = s.outreach_reply_to or from_addr
        return cls(
            sender_name=s.outreach_sender_name,
            physical_address=s.outreach_physical_address,
            reply_to=reply_to,
        )


def ensure_can_spam_ready(cfg: CanSpamConfig | None = None) -> CanSpamConfig:
    """Raise MissingComplianceField if any required element is missing."""
    cfg = cfg or CanSpamConfig.from_settings()
    if not cfg.physical_address.strip():
        raise MissingComplianceField(
            "GS_OUTREACH_PHYSICAL_ADDRESS is empty. CAN-SPAM requires a real postal address "
            "in every commercial email. Set it in .env before sending."
        )
    if not cfg.reply_to.strip():
        raise MissingComplianceField(
            "No reply-to / from address configured. Set GS_OUTREACH_FROM or GS_NOTIFY_FROM."
        )
    return cfg


def footer_text(cfg: CanSpamConfig) -> str:
    """Plain-text footer added to every outreach email."""
    return (
        "\n\n---\n"
        f"This email was sent by {cfg.sender_name} <{cfg.reply_to}>.\n"
        "To stop receiving these inquiries, reply to this email with the word "
        '"UNSUBSCRIBE" anywhere in the body.\n'
        f"Mailing address: {cfg.physical_address}\n"
    )


def footer_html(cfg: CanSpamConfig) -> str:
    return (
        "<hr style=\"margin-top:24px;border:none;border-top:1px solid #ddd\">"
        "<p style=\"font-size:12px;color:#666;font-family:-apple-system,Segoe UI,sans-serif\">"
        f"This email was sent by {escape(cfg.sender_name)} "
        f"&lt;{escape(cfg.reply_to)}&gt;. "
        "To stop receiving these inquiries, reply with the word "
        "<strong>UNSUBSCRIBE</strong> anywhere in the body.<br>"
        f"Mailing address: {escape(cfg.physical_address)}"
        "</p>"
    )


_UNSUBSCRIBE_TOKENS: tuple[str, ...] = (
    "unsubscribe",
    "remove me",
    "take me off",
    "stop emailing",
    "do not email",
    "opt out",
    "opt-out",
)


def looks_like_unsubscribe(reply_body: str) -> bool:
    """Cheap heuristic for opt-out intent in a reply body."""
    if not reply_body:
        return False
    lower = reply_body.lower()
    return any(token in lower for token in _UNSUBSCRIBE_TOKENS)
