from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from guitar_searcher.db.seed import _to_row
from guitar_searcher.db.session import get_session
from guitar_searcher.models.outreach import OutreachAttemptRow
from guitar_searcher.outreach.queue import (
    approve_draft,
    create_draft_attempts,
    eligible_outreach_shops,
    record_opt_out,
)
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.schemas.shop import InventoryStrategy, Shop, ShopClassification


def _shop(**overrides: object) -> Shop:
    defaults = dict(
        name="Test",
        domain="testshop.com",
        website_url="https://testshop.com",
        email="hi@testshop.com",
        inventory_strategy=InventoryStrategy.EMAIL_ONLY,
        classification=ShopClassification.BOUTIQUE,
        active=True,
    )
    defaults.update(overrides)
    return Shop(**defaults)  # type: ignore[arg-type]


def _setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GS_OUTREACH_PHYSICAL_ADDRESS", "PO Box 1, Indy, IN 46201")
    monkeypatch.setenv("GS_OUTREACH_FROM", "user@example.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GS_OUTREACH_COOLDOWN_DAYS", "30")
    from guitar_searcher.config import get_settings
    from guitar_searcher.llm.client import get_anthropic_client

    get_settings.cache_clear()
    get_anthropic_client.cache_clear()


def test_eligibility_filters_inactive_and_no_email(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_env(monkeypatch)
    with get_session() as s:
        s.add(_to_row(_shop(domain="a.com", email="a@a.com", active=True)))
        s.add(_to_row(_shop(domain="b.com", email=None, active=True)))
        s.add(_to_row(_shop(domain="c.com", email="c@c.com", active=False)))
        s.add(
            _to_row(
                _shop(
                    domain="d.com",
                    email="d@d.com",
                    inventory_strategy=InventoryStrategy.SHOPIFY_JSON,
                )
            )
        )
    with get_session() as s:
        eligible = eligible_outreach_shops(s)
    domains = {sh.domain for sh in eligible}
    assert domains == {"a.com"}


def test_cooldown_excludes_recent(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_env(monkeypatch)
    with get_session() as s:
        s.add(_to_row(_shop(domain="a.com", email="a@a.com")))
        s.flush()
        from sqlalchemy import select as sa_select

        from guitar_searcher.models.shop import ShopRow
        shop_id = s.execute(sa_select(ShopRow.id).where(ShopRow.domain == "a.com")).scalar_one()
        s.add(
            OutreachAttemptRow(
                shop_id=shop_id,
                channel="email",
                template_id="initial_inquiry",
                subject="x",
                message_body="x",
                from_addr="u@example.com",
                to_addr="a@a.com",
                status="sent",
                sent_at=datetime.now(UTC) - timedelta(days=5),
            )
        )
    with get_session() as s:
        eligible = eligible_outreach_shops(s)
    assert eligible == []


def test_cooldown_expired_includes(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_env(monkeypatch)
    with get_session() as s:
        s.add(_to_row(_shop(domain="a.com", email="a@a.com")))
        s.flush()
        from sqlalchemy import select as sa_select

        from guitar_searcher.models.shop import ShopRow
        shop_id = s.execute(sa_select(ShopRow.id).where(ShopRow.domain == "a.com")).scalar_one()
        s.add(
            OutreachAttemptRow(
                shop_id=shop_id,
                channel="email",
                template_id="initial_inquiry",
                subject="x",
                message_body="x",
                from_addr="u@example.com",
                to_addr="a@a.com",
                status="sent",
                sent_at=datetime.now(UTC) - timedelta(days=45),
            )
        )
    with get_session() as s:
        eligible = eligible_outreach_shops(s)
    assert {sh.domain for sh in eligible} == {"a.com"}


def test_opted_out_excluded(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_env(monkeypatch)
    with get_session() as s:
        s.add(_to_row(_shop(domain="a.com", email="a@a.com")))
        s.flush()
        from sqlalchemy import select as sa_select

        from guitar_searcher.models.shop import ShopRow
        shop_id = s.execute(sa_select(ShopRow.id).where(ShopRow.domain == "a.com")).scalar_one()
        record_opt_out(s, shop_id, source="reply")
    with get_session() as s:
        eligible = eligible_outreach_shops(s)
    assert eligible == []


def test_create_drafts_then_approve(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_env(monkeypatch)
    with get_session() as s:
        s.add(_to_row(_shop(domain="a.com", email="a@a.com")))
    with get_session() as s:
        shops = eligible_outreach_shops(s)
        drafts = create_draft_attempts(
            s,
            search_id=None,
            query=QuerySpec(brand="Fender", model="Jaguar"),
            shops=shops,
            use_llm_personalization=False,
        )
        assert len(drafts) == 1
        draft_id = drafts[0].id
        assert drafts[0].status == "draft"

    with get_session() as s:
        approve_draft(s, draft_id)
    with get_session() as s:
        row = s.get(OutreachAttemptRow, draft_id)
        assert row is not None
        assert row.status == "queued"
        assert row.approved_by_user_at is not None
