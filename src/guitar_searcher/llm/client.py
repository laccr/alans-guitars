from __future__ import annotations

from functools import lru_cache

from anthropic import Anthropic

from guitar_searcher.config import get_settings

CLAUDE_MODEL = "claude-haiku-4-5-20251001"


@lru_cache(maxsize=1)
def get_anthropic_client() -> Anthropic | None:
    """Return a configured Anthropic client, or None if no API key is set."""
    key = get_settings().anthropic_api_key
    if not key:
        return None
    return Anthropic(api_key=key)
