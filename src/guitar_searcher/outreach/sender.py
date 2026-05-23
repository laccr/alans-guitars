"""Send an approved outreach attempt via SMTP. Hard-gates on CAN-SPAM and opt-out."""
from __future__ import annotations

import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from guitar_searcher.config import get_settings
from guitar_searcher.models.outreach import OptOutRow, OutreachAttemptRow
from guitar_searcher.outreach.compliance import ensure_can_spam_ready
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)


class OutreachSendError(RuntimeError):
    """Generic failure during send."""


class PhysicalAddressMissing(OutreachSendError):
    """Raised when GS_OUTREACH_PHYSICAL_ADDRESS is empty at send time."""


def send_outreach_attempt(
    session: Session, attempt_id: int, *, dry_run: bool = False
) -> OutreachAttemptRow:
    """Send a single approved attempt. Refuses if missing CAN-SPAM data or shop opted out."""
    attempt = session.get(OutreachAttemptRow, attempt_id)
    if attempt is None:
        raise LookupError(f"No attempt {attempt_id}")
    if attempt.status not in {"queued", "draft"}:
        raise ValueError(f"attempt {attempt_id} not sendable (status={attempt.status})")
    if attempt.status == "draft" and not dry_run:
        raise ValueError(f"attempt {attempt_id} not approved; status must be 'queued'")

    # CAN-SPAM check.
    try:
        ensure_can_spam_ready()
    except RuntimeError as exc:
        attempt.status = "failed"
        attempt.error = str(exc)
        raise PhysicalAddressMissing(str(exc)) from exc

    # Opt-out check (could have been recorded after the draft was created).
    opted_out = session.execute(
        select(OptOutRow).where(OptOutRow.shop_id == attempt.shop_id)
    ).scalar_one_or_none()
    if opted_out is not None:
        attempt.status = "suppressed"
        attempt.error = "shop is opted out"
        raise OutreachSendError(f"shop {attempt.shop_id} is opted out")

    settings = get_settings()
    if not all([settings.smtp_host, settings.smtp_username, settings.smtp_password]):
        attempt.status = "failed"
        attempt.error = "SMTP not configured"
        raise OutreachSendError("SMTP not configured; see GS_SMTP_* settings")

    msg = EmailMessage()
    msg["From"] = f"{settings.outreach_sender_name} <{attempt.from_addr}>"
    msg["To"] = attempt.to_addr
    msg["Reply-To"] = settings.outreach_reply_to or attempt.from_addr
    msg["Subject"] = attempt.subject
    if attempt.message_id_header:
        msg["Message-ID"] = attempt.message_id_header
    msg.set_content(attempt.message_body)
    if attempt.message_html:
        msg.add_alternative(attempt.message_html, subtype="html")

    if dry_run:
        log.info("outreach.dry_run", attempt_id=attempt_id, to=attempt.to_addr)
        attempt.status = "dry_run"
        return attempt

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as srv:
            if settings.smtp_use_tls:
                srv.starttls(context=ctx)
            srv.login(settings.smtp_username, settings.smtp_password)
            srv.send_message(msg)
    except Exception as exc:
        attempt.status = "failed"
        attempt.error = str(exc)
        log.error("outreach.send_failed", attempt_id=attempt_id, error=str(exc))
        raise OutreachSendError(str(exc)) from exc

    attempt.status = "sent"
    attempt.sent_at = datetime.now(UTC)
    log.info("outreach.sent", attempt_id=attempt_id, to=attempt.to_addr)
    return attempt
