from __future__ import annotations

import pytest

from guitar_searcher.outreach.classifier import classify_reply


def test_unsubscribe_heuristic_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    # No ANTHROPIC key -> LLM path is None, but heuristic catches first.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from guitar_searcher.config import get_settings
    from guitar_searcher.llm.client import get_anthropic_client

    get_settings.cache_clear()
    get_anthropic_client.cache_clear()

    result = classify_reply("Please UNSUBSCRIBE me from this list.")
    assert result["classification"] == "unsubscribe"
    assert result["follow_up_needed"] is False


def test_no_llm_falls_back_to_unclear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from guitar_searcher.config import get_settings
    from guitar_searcher.llm.client import get_anthropic_client

    get_settings.cache_clear()
    get_anthropic_client.cache_clear()

    result = classify_reply("Yes! We have one in stock for $20,000, plays great.")
    assert result["classification"] == "unclear"
    assert result["follow_up_needed"] is True
