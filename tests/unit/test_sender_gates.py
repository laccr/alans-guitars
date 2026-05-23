from __future__ import annotations

import pytest

from guitar_searcher.db.seed import _to_row
from guitar_searcher.db.session import get_session
from guitar_searcher.models.outreach import OptOutRow, OutreachAttemptRow
from guitar_searcher.outreach.sender import (
    OutreachSendError,
    PhysicalAddressMissing,
    send_outreach_attempt,
)
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


def _new_attempt(session, shop_id: int) -> OutreachAttemptRow:  # type: ignore[no-untyped-def]
    row = OutreachAttemptRow(
        shop_id=shop_id,
        channel="email",
        template_id="initial_inquiry",
        subject="x",
        message_body="hello",
        from_addr="user@example.com",
        to_addr="hi@testshop.com",
        status="queued",
    )
    session.add(row)
    session.flush()
    return row


def test_send_refuses_without_physical_address(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GS_OUTREACH_PHYSICAL_ADDRESS", "")
    monkeypatch.setenv("GS_OUTREACH_FROM", "u@example.com")
    from guitar_searcher.config import get_settings

    get_settings.cache_clear()

    with get_session() as s:
        s.add(_to_row(_shop()))
        s.flush()
        from sqlalchemy import select as sa_select

        from guitar_searcher.models.shop import ShopRow
        shop_id = s.execute(sa_select(ShopRow.id).where(ShopRow.domain == "testshop.com")).scalar_one()
        attempt = _new_attempt(s, shop_id)
        attempt_id = attempt.id

    with pytest.raises(PhysicalAddressMissing), get_session() as s:
        send_outreach_attempt(s, attempt_id)


def test_send_refuses_when_draft(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GS_OUTREACH_PHYSICAL_ADDRESS", "PO Box 1, Indy, IN 46201")
    monkeypatch.setenv("GS_OUTREACH_FROM", "u@example.com")
    from guitar_searcher.config import get_settings

    get_settings.cache_clear()

    with get_session() as s:
        s.add(_to_row(_shop()))
        s.flush()
        from sqlalchemy import select as sa_select

        from guitar_searcher.models.shop import ShopRow
        shop_id = s.execute(sa_select(ShopRow.id).where(ShopRow.domain == "testshop.com")).scalar_one()
        attempt = _new_attempt(s, shop_id)
        attempt.status = "draft"
        s.flush()
        attempt_id = attempt.id

    with pytest.raises(ValueError), get_session() as s:
        send_outreach_attempt(s, attempt_id)


def test_send_dry_run_does_not_require_smtp(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GS_OUTREACH_PHYSICAL_ADDRESS", "PO Box 1, Indy, IN 46201")
    monkeypatch.setenv("GS_OUTREACH_FROM", "u@example.com")
    monkeypatch.setenv("GS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("GS_SMTP_USERNAME", "u")
    monkeypatch.setenv("GS_SMTP_PASSWORD", "p")
    from guitar_searcher.config import get_settings

    get_settings.cache_clear()

    with get_session() as s:
        s.add(_to_row(_shop()))
        s.flush()
        from sqlalchemy import select as sa_select

        from guitar_searcher.models.shop import ShopRow
        shop_id = s.execute(sa_select(ShopRow.id).where(ShopRow.domain == "testshop.com")).scalar_one()
        attempt = _new_attempt(s, shop_id)
        attempt_id = attempt.id

    with get_session() as s:
        result = send_outreach_attempt(s, attempt_id, dry_run=True)
        assert result.status == "dry_run"


def test_send_blocks_opted_out_shop(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    monkeypatch.setenv("GS_OUTREACH_PHYSICAL_ADDRESS", "PO Box 1, Indy, IN 46201")
    monkeypatch.setenv("GS_OUTREACH_FROM", "u@example.com")
    monkeypatch.setenv("GS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("GS_SMTP_USERNAME", "u")
    monkeypatch.setenv("GS_SMTP_PASSWORD", "p")
    from guitar_searcher.config import get_settings

    get_settings.cache_clear()

    with get_session() as s:
        s.add(_to_row(_shop()))
        s.flush()
        from sqlalchemy import select as sa_select

        from guitar_searcher.models.shop import ShopRow
        shop_id = s.execute(sa_select(ShopRow.id).where(ShopRow.domain == "testshop.com")).scalar_one()
        attempt = _new_attempt(s, shop_id)
        attempt_id = attempt.id
        s.add(
            OptOutRow(
                shop_id=shop_id,
                source="reply",
                recorded_at=datetime.now(UTC),
            )
        )

    with pytest.raises(OutreachSendError), get_session() as s:
        send_outreach_attempt(s, attempt_id)
