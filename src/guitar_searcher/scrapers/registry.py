from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from guitar_searcher.scrapers.base import AbstractScraper

_registry: dict[str, type[AbstractScraper]] = {}


def register_scraper(cls: type[AbstractScraper]) -> type[AbstractScraper]:
    """Decorator to register a scraper class by its `name` attribute."""
    if not getattr(cls, "name", None):
        raise ValueError(f"{cls.__name__} must set a non-empty `name` class attribute")
    if cls.name in _registry:
        raise ValueError(f"Scraper {cls.name!r} already registered")
    _registry[cls.name] = cls
    return cls


def get_scraper(name: str) -> type[AbstractScraper]:
    _ensure_loaded()
    if name not in _registry:
        raise KeyError(f"No scraper registered with name {name!r}")
    return _registry[name]


def enabled_scrapers() -> dict[str, type[AbstractScraper]]:
    _ensure_loaded()
    return dict(_registry)


_loaded = False


def _ensure_loaded() -> None:
    """Import every module under guitar_searcher.scrapers so decorators register their classes."""
    global _loaded
    if _loaded:
        return
    import guitar_searcher.scrapers as pkg

    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name in {"base", "registry"}:
            continue
        importlib.import_module(f"{pkg.__name__}.{mod.name}")
    _loaded = True
