# guitar-searcher

Hunt for specific guitars across the US guitar retail web.

## What it does

Given a query like *"1962 Fender Jaguar, sunburst, under $25,000"*, this tool fans out across:

- **Tier A** — Reverb's official API.
- **Tier B** — hand-written scrapers for major retailers (Sweetwater, Wildwood, Carter Vintage, Elderly) and a generic Shopify `/products.json` scraper that picks up many boutique shops automatically.
- **Tier C** *(Phase 2b)* — Playwright + LLM-assisted extraction for irregular small-shop sites.
- **Tier D** *(Phase 3)* — email/contact-form outreach to shops whose inventory isn't crawlable. Replies are parsed by an LLM classifier.

Results are normalized, deduped across sources, scored against the query, and returned as a ranked list. Saved "watch" searches (Phase 2) re-run on a schedule and email new matches.

AI voice outreach (Phase 4) exists as an **opt-in feature, per-call user-approved**, with a hardcoded FCC-compliant disclosure as the first turn — because the Feb 2024 FCC TCPA ruling makes cold AI calls legally risky.

## Install

Requires Python 3.11+.

```powershell
pip install -e ".[dev]"
# Optional, only needed for scrapers that require a real browser:
pip install -e ".[browser]"
playwright install chromium
```

Or, with [uv](https://docs.astral.sh/uv/):

```powershell
uv sync --extra dev
```

## Setup

```powershell
Copy-Item .env.example .env
# Fill in REVERB_TOKEN, ANTHROPIC_API_KEY, etc.

alembic upgrade head
guitar-searcher shops seed
```

## Usage

```powershell
guitar-searcher search `
    --brand Fender `
    --model Jaguar `
    --year-min 1960 --year-max 1965 `
    --finish sunburst `
    --max-price 25000
```

You'll get a ranked Rich table of hits: shop, URL, price, year (with confidence), condition, and a one-line "why it matched" note.

## Layout

```
src/guitar_searcher/
  config.py              # pydantic-settings
  cli/                   # Typer commands
  schemas/               # Pydantic contracts (QuerySpec, NormalizedListing, Shop)
  models/                # SQLAlchemy ORM
  db/                    # session + seed loader; seed_data/*.yaml
  scrapers/              # base protocol + per-source adapters
  matching/              # normalize, fingerprint, score, llm_tiebreaker
  llm/                   # Anthropic SDK wrapper with prompt caching
  utils/                 # rate limiting, logging
```

## Docs

- [docs/STATUS.md](docs/STATUS.md) — current state, what works, what's blocked.
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — exact commands for every common workflow.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system overview, module map, data contracts.

## Status

Phases 1, 2, 2b, 2c, 3 are merged. End-to-end validated against live Reverb API + Gmail SMTP/IMAP. Phase 4 (opt-in AI voice calls) is not started. See `docs/STATUS.md` for current detail.
