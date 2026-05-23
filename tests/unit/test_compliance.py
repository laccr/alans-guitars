from __future__ import annotations

import pytest

from guitar_searcher.outreach.compliance import (
    CanSpamConfig,
    MissingComplianceField,
    ensure_can_spam_ready,
    footer_html,
    footer_text,
    looks_like_unsubscribe,
)


def _cfg(**overrides: str) -> CanSpamConfig:
    defaults = {
        "sender_name": "Guitar Searcher",
        "physical_address": "123 Main St, Springfield, IL 62701",
        "reply_to": "user@example.com",
    }
    defaults.update(overrides)
    return CanSpamConfig(**defaults)


def test_footer_text_includes_required_elements() -> None:
    text = footer_text(_cfg())
    assert "UNSUBSCRIBE" in text
    assert "123 Main St" in text
    assert "user@example.com" in text


def test_footer_html_includes_required_elements() -> None:
    html = footer_html(_cfg())
    assert "UNSUBSCRIBE" in html
    assert "123 Main St" in html
    assert "user@example.com" in html


def test_ensure_blocks_when_address_missing() -> None:
    with pytest.raises(MissingComplianceField):
        ensure_can_spam_ready(_cfg(physical_address=""))


def test_ensure_blocks_when_reply_to_missing() -> None:
    with pytest.raises(MissingComplianceField):
        ensure_can_spam_ready(_cfg(reply_to=""))


def test_ensure_passes_when_all_set() -> None:
    cfg = ensure_can_spam_ready(_cfg())
    assert cfg.physical_address.startswith("123")


def test_unsubscribe_heuristic_positives() -> None:
    for body in [
        "please UNSUBSCRIBE me",
        "remove me from your list",
        "stop emailing us, thanks",
        "opt out please",
        "Do Not Email me again.",
    ]:
        assert looks_like_unsubscribe(body), body


def test_unsubscribe_heuristic_negatives() -> None:
    for body in [
        "Yes, we have one in stock!",
        "Sorry, we don't have that guitar.",
        "",
    ]:
        assert not looks_like_unsubscribe(body), body
