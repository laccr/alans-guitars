"""Outreach draft queue.

Eligibility for inquiry:
  - shop is active
  - shop has an email address
  - inventory_strategy in {email_only, generic_crawler, unknown}
    (we only email shops we can't crawl for; not shops on Reverb/Shopify)
  - not opted out
  - no attempt to this shop within the cooldown window

Drafts are NEVER auto-sent. They land in outreach_attempts with status='draft' and
require explicit CLI approval before status flips to 'queued', then 'sent'.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from guitar_searcher.config import get_settings
from guitar_searcher.db.seed import row_to_shop
from guitar_searcher.models.outreach import OptOutRow, OutreachAttemptRow
from guitar_searcher.models.shop import ShopRow
from guitar_searcher.outreach.composer import compose_initial_inquiry
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.schemas.shop import InventoryStrategy, Shop
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)

_EMAIL_ELIGIBLE_STRATEGIES = {
    InventoryStrategy.EMAIL_ONLY.value,
    InventoryStrategy.GENERIC_CRAWLER.value,  # crawl is Phase 2b; email is the fallback today
    InventoryStrategy.NONE.value,
}


class CooldownActive(RuntimeError):
    """Shop has an attempt within the cooldown window."""


class OptedOut(RuntimeError):
    """Shop has opted out and must not be contacted."""


def eligible_outreach_shops(session: Session) -> list[Shop]:
    rows = session.execute(
        select(ShopRow).where(
            ShopRow.active.is_(True),
            ShopRow.email.is_not(None),
            ShopRow.email != "",
            ShopRow.inventory_strategy.in_(_EMAIL_ELIGIBLE_STRATEGIES),
        )
    ).scalars().all()

    opted_out_ids = {
        sid for (sid,) in session.execute(select(OptOutRow.shop_id)).all()
    }

    cooldown_days = get_settings().outreach_cooldown_days
    cutoff = datetime.now(UTC) - timedelta(days=cooldown_days)
    recent_ids = {
        sid
        for (sid,) in session.execute(
            select(OutreachAttemptRow.shop_id).where(
                OutreachAttemptRow.sent_at.is_not(None),
                OutreachAttemptRow.sent_at >= cutoff,
            )
        ).all()
    }

    return [
        row_to_shop(r)
        for r in rows
        if r.id not in opted_out_ids and r.id not in recent_ids
    ]


def create_draft_attempts(
    session: Session,
    *,
    search_id: int | None,
    query: QuerySpec,
    shops: list[Shop],
    use_llm_personalization: bool = True,
) -> list[OutreachAttemptRow]:
    """Compose drafts for each shop and persist with status='draft'."""
    settings = get_settings()
    from_addr = settings.outreach_from or settings.notify_from
    if not from_addr:
        raise RuntimeError("No outreach From address; set GS_OUTREACH_FROM or GS_NOTIFY_FROM.")

    drafts: list[OutreachAttemptRow] = []
    for shop in shops:
        if not shop.email:
            continue
        # Map shop pydantic back to a row id by domain (drafts need shop_id).
        row = session.execute(
            select(ShopRow.id).where(ShopRow.domain == shop.domain)
        ).scalar_one_or_none()
        if row is None:
            log.warning("draft.shop_not_persisted", domain=shop.domain)
            continue

        msg = compose_initial_inquiry(
            shop=shop, query=query, use_llm_personalization=use_llm_personalization
        )
        attempt = OutreachAttemptRow(
            shop_id=row,
            search_id=search_id,
            channel="email",
            template_id="initial_inquiry",
            subject=msg.subject,
            message_body=msg.text_body,
            message_html=msg.html_body,
            from_addr=from_addr,
            to_addr=msg.to_addr,
            message_id_header=msg.message_id,
            status="draft",
        )
        session.add(attempt)
        drafts.append(attempt)
    session.flush()
    return drafts


def approve_draft(session: Session, attempt_id: int) -> OutreachAttemptRow:
    row = session.get(OutreachAttemptRow, attempt_id)
    if row is None:
        raise LookupError(f"No outreach attempt {attempt_id}")
    if row.status != "draft":
        raise ValueError(f"attempt {attempt_id} is not a draft (status={row.status})")
    row.status = "queued"
    row.approved_by_user_at = datetime.now(UTC)
    session.flush()
    return row


def record_opt_out(session: Session, shop_id: int, *, source: str, note: str | None = None) -> None:
    existing = session.execute(
        select(OptOutRow).where(OptOutRow.shop_id == shop_id)
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        OptOutRow(
            shop_id=shop_id,
            source=source,
            note=note,
            recorded_at=datetime.now(UTC),
        )
    )
    session.flush()
