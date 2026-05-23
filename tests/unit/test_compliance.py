from __future__ import annotations

import pytest

from guitar_searcher.outreach.compliance import (
    CanSpamConfig,
    MissingComplianceField,
    ensure_can_spam_ready,
    footer_html,
    footer_text,
    looks_like_unsubscribe,
    strip_quoted_reply,
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


def test_unsubscribe_ignores_quoted_footer() -> None:
    """A reply whose body says 'No' but quotes our own UNSUBSCRIBE footer should NOT
    be flagged as unsubscribe. This was a real false-positive in production testing."""
    reply = """I do not have that guitar, but please try Alan's Guitars.

On Sat, May 23, 2026 at 1:23 PM Troy <troy@littlestudybuddy.com> wrote:

> Hi Test Shop team,
> ... boilerplate ...
> reply with the word UNSUBSCRIBE anywhere in the body.
> Mailing address: 6255 Aventura Drive, Sarasota, FL 34241
"""
    assert not looks_like_unsubscribe(reply)


def test_strip_quoted_reply_removes_quoted_block() -> None:
    reply = (
        "I do not have that guitar, but please try Alan's Guitars.\n"
        "\n"
        "On Sat, May 23, 2026 at 1:23 PM Troy <troy@littlestudybuddy.com> wrote:\n"
        ">\n"
        "> Hi Test Shop team,\n"
        "> reply with the word UNSUBSCRIBE\n"
    )
    new = strip_quoted_reply(reply)
    assert "I do not have that guitar" in new
    assert "Hi Test Shop team" not in new
    assert "UNSUBSCRIBE" not in new


def test_strip_quoted_reply_handles_outlook_original_message() -> None:
    reply = (
        "No, we don't have it.\n\n"
        "-----Original Message-----\n"
        "From: Troy\n"
        "Subject: Inquiring about ...\n"
        "reply with UNSUBSCRIBE\n"
    )
    new = strip_quoted_reply(reply)
    assert "No, we don't have it." in new
    assert "Original Message" not in new


def test_strip_quoted_reply_empty_input() -> None:
    assert strip_quoted_reply("") == ""
