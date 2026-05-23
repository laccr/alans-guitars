from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Use a per-test SQLite file so tests don't stomp on the dev DB.
os.environ.setdefault("GS_DATABASE_URL", "sqlite:///./guitar_searcher_test.db")


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Point the engine at a temp SQLite file and create tables."""
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("GS_DATABASE_URL", url)

    # Force settings cache to refresh.
    from guitar_searcher.config import get_settings

    get_settings.cache_clear()

    # Rebuild engine and session against new URL.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import guitar_searcher.db.session as session_mod

    session_mod.engine = create_engine(url, future=True)
    session_mod.SessionLocal = sessionmaker(
        bind=session_mod.engine, autoflush=False, expire_on_commit=False, future=True
    )

    from guitar_searcher.models.base import Base

    Base.metadata.create_all(bind=session_mod.engine)
    try:
        yield url
    finally:
        session_mod.engine.dispose()
