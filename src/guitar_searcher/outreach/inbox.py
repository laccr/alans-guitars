"""IMAP poll for replies to outreach attempts.

Strategy: connect, search UNSEEN, fetch each, look at In-Reply-To and References headers
to find the originating outreach_attempt by message_id_header, persist the reply, mark
the email \\Seen so we don't reprocess.
"""
from __future__ import annotations

import email
import imaplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message

from sqlalchemy import select
from sqlalchemy.orm import Session

from guitar_searcher.config import get_settings
from guitar_searcher.models.outreach import OutreachAttemptRow, OutreachReplyRow
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)


class ImapNotConfigured(RuntimeError):
    """Raised when IMAP env vars are not populated."""


@dataclass
class PollResult:
    examined: int = 0
    matched_replies: int = 0
    unmatched: int = 0


def poll_replies(session: Session, *, mark_seen: bool = True) -> PollResult:
    settings = get_settings()
    if not all([settings.imap_host, settings.imap_username, settings.imap_password]):
        raise ImapNotConfigured(
            "IMAP not configured. Set GS_IMAP_HOST / GS_IMAP_USERNAME / GS_IMAP_PASSWORD."
        )

    ctx = ssl.create_default_context()
    result = PollResult()
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, ssl_context=ctx) as imap:
        imap.login(settings.imap_username, settings.imap_password)
        imap.select(settings.imap_mailbox)
        status, data = imap.search(None, "UNSEEN")
        if status != "OK":
            log.warning("inbox.search_failed", status=status)
            return result
        uids = data[0].split()
        log.info("inbox.unseen", count=len(uids))

        for uid in uids:
            result.examined += 1
            status, msg_data = imap.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else None
            if not isinstance(raw, bytes):
                continue
            message = email.message_from_bytes(raw)
            attempt = _match_attempt(session, message)
            if attempt is None:
                result.unmatched += 1
                continue
            _save_reply(session, attempt, message)
            result.matched_replies += 1
            if mark_seen:
                imap.store(uid, "+FLAGS", "\\Seen")
        session.commit()
    return result


def _match_attempt(session: Session, message: Message) -> OutreachAttemptRow | None:
    """Find the outreach_attempt this reply is responding to via header threading."""
    candidates: list[str] = []
    in_reply_to = message.get("In-Reply-To")
    if in_reply_to:
        candidates.append(in_reply_to.strip())
    refs = message.get("References") or ""
    for ref in refs.split():
        ref = ref.strip()
        if ref:
            candidates.append(ref)
    # Also try the To header (the reply's To should be our outreach From; weak signal but better than nothing)

    for header_value in candidates:
        attempt = session.execute(
            select(OutreachAttemptRow).where(OutreachAttemptRow.message_id_header == header_value)
        ).scalar_one_or_none()
        if attempt is not None:
            return attempt
    return None


def _save_reply(session: Session, attempt: OutreachAttemptRow, message: Message) -> None:
    body = _extract_plain_body(message)
    reply = OutreachReplyRow(
        attempt_id=attempt.id,
        received_at=datetime.now(UTC),
        raw_body=body,
        classification="unclear",
        follow_up_needed=False,
    )
    session.add(reply)
    if attempt.status == "sent":
        attempt.status = "replied"


def _extract_plain_body(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    try:
                        return payload.decode(charset, errors="replace")
                    except LookupError:
                        return payload.decode("utf-8", errors="replace")
        # Fallback to first text/html part stripped naively
        for part in message.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(charset, errors="replace")
        return ""
    payload = message.get_payload(decode=True)
    if isinstance(payload, bytes):
        charset = message.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except LookupError:
            return payload.decode("utf-8", errors="replace")
    return str(message.get_payload() or "")
