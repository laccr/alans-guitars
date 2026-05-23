from __future__ import annotations

import pytest

from guitar_searcher.outreach.composer import compose_initial_inquiry
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.schemas.shop import InventoryStrategy, Shop, ShopClassification


def _shop(**overrides: object) -> Shop:
    defaults = dict(
        name="Test Vintage",
        domain="testvintage.com",
        website_url="https://testvintage.com",
        email="hello@testvintage.com",
        city="Nashville",
        state="TN",
        classification=ShopClassification.VINTAGE_SPECIALIST,
        inventory_strategy=InventoryStrategy.EMAIL_ONLY,
        active=True,
    )
    defaults.update(overrides)
    return Shop(**defaults)  # type: ignore[arg-type]


def _setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GS_OUTREACH_PHYSICAL_ADDRESS", "1 Main St, Indianapolis, IN 46201")
    monkeypatch.setenv("GS_OUTREACH_FROM", "user@example.com")
    monkeypatch.setenv("GS_OUTREACH_SIGNER_NAME", "Brent Scott")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # disable LLM path
    from guitar_searcher.config import get_settings
    from guitar_searcher.llm.client import get_anthropic_client

    get_settings.cache_clear()
    get_anthropic_client.cache_clear()


def test_compose_includes_query_and_footer(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_env(monkeypatch)
    msg = compose_initial_inquiry(
        shop=_shop(),
        query=QuerySpec(brand="Fender", model="Jaguar", year_min=1962, year_max=1965, max_price_usd=25000),
        use_llm_personalization=False,
    )
    assert "Fender Jaguar" in msg.text_body
    assert "$25,000" in msg.text_body
    assert "UNSUBSCRIBE" in msg.text_body
    assert "1 Main St, Indianapolis" in msg.text_body
    assert msg.subject.startswith("Inquiring about")
    assert msg.to_addr == "hello@testvintage.com"
    assert msg.message_id.startswith("<") and msg.message_id.endswith("@guitar-searcher>")


def test_compose_all_original_phrasing(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_env(monkeypatch)
    msg = compose_initial_inquiry(
        shop=_shop(),
        query=QuerySpec(brand="Fender", model="Jaguar", all_original_only=True),
        use_llm_personalization=False,
    )
    assert "all-original" in msg.text_body.lower()


def test_compose_refuses_without_email(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_env(monkeypatch)
    with pytest.raises(ValueError):
        compose_initial_inquiry(
            shop=_shop(email=None), query=QuerySpec(), use_llm_personalization=False
        )


def test_compose_refuses_without_physical_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GS_OUTREACH_PHYSICAL_ADDRESS", "")
    monkeypatch.setenv("GS_OUTREACH_FROM", "user@example.com")
    monkeypatch.setenv("GS_OUTREACH_SIGNER_NAME", "Brent Scott")
    from guitar_searcher.config import get_settings

    get_settings.cache_clear()
    from guitar_searcher.outreach.compliance import MissingComplianceField

    with pytest.raises(MissingComplianceField):
        compose_initial_inquiry(
            shop=_shop(), query=QuerySpec(), use_llm_personalization=False
        )


def test_compose_refuses_without_signer_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GS_OUTREACH_PHYSICAL_ADDRESS", "1 Main St, Indy, IN 46201")
    monkeypatch.setenv("GS_OUTREACH_FROM", "user@example.com")
    monkeypatch.setenv("GS_OUTREACH_SIGNER_NAME", "")
    from guitar_searcher.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(ValueError, match="GS_OUTREACH_SIGNER_NAME"):
        compose_initial_inquiry(
            shop=_shop(), query=QuerySpec(), use_llm_personalization=False
        )
