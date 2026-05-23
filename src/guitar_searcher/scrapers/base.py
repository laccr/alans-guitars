from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from guitar_searcher.schemas import NormalizedListing, QuerySpec, Shop
from guitar_searcher.utils.ratelimit import HostRateLimiter


@dataclass
class ScraperContext:
    """Shared resources passed to every scraper invocation."""

    client: httpx.AsyncClient
    rate_limiter: HostRateLimiter
    user_agent: str
    timeout_s: float = 30.0


@dataclass
class ScraperResult:
    """Output of a single scraper run."""

    scraper_name: str
    listings: list[NormalizedListing] = field(default_factory=list)
    examined: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class AbstractScraper(ABC):
    """Every Tier A/B scraper implements this interface."""

    #: Stable, unique name. Used in the registry and persisted with listings.
    name: str

    #: Human-readable display name.
    display: str = ""

    #: When True, applies generically to any seeded shop (no shop binding required).
    is_generic: bool = False

    @abstractmethod
    async def search(
        self, query: QuerySpec, ctx: ScraperContext, shop: Shop | None = None
    ) -> ScraperResult:
        """Run a search against this source. `shop` is provided for shop-bound scrapers."""
        raise NotImplementedError
