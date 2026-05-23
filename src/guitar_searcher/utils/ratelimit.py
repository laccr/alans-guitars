from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

from aiolimiter import AsyncLimiter


class HostRateLimiter:
    """Per-host token-bucket limiter. Polite by default — one shared bucket per hostname."""

    def __init__(self, rps: float, burst: int | None = None) -> None:
        self._rps = rps
        self._burst = burst or max(1, int(rps))
        self._limiters: dict[str, AsyncLimiter] = {}

    def _host(self, url: str) -> str:
        return urlparse(url).hostname or ""

    def for_url(self, url: str) -> AsyncLimiter:
        host = self._host(url)
        limiter = self._limiters.get(host)
        if limiter is None:
            limiter = AsyncLimiter(self._burst, 1.0 / self._rps if self._rps > 0 else 1.0)
            self._limiters[host] = limiter
        return limiter

    async def acquire(self, url: str) -> None:
        limiter = self.for_url(url)
        await limiter.acquire()

    @property
    def stats(self) -> Mapping[str, float]:
        return {host: lim.max_rate for host, lim in self._limiters.items()}
