# Architecture

## Big picture

A single-user CLI that hunts for specific guitars across the US guitar retail web in four tiers, plus a notification + outreach layer.

```
┌────────────────────┐    ┌─────────────────┐
│ Typer CLI          │    │ APScheduler     │
│ (search/watch/...) │    │ daemon          │
└────────┬───────────┘    └────────┬────────┘
         │                         │
         ▼                         ▼
┌──────────────────────────────────────────┐
│ search_runner.run_search(QuerySpec)      │
│ watch_runner.run_watch_async(watch)      │
└────────┬─────────────────────────────────┘
         │ fan-out async
         ▼
┌──────────────────────────────────────────┐
│ scrapers/  registry-driven adapters      │
│   Tier A  reverb_api      (one-shot)     │
│   Tier B  shopify_generic (per shop)     │
│           sweetwater, wildwood,          │
│           carter_vintage, elderly        │
│           (dormant; WAF-blocked)         │
│   Tier C  generic_crawler (deferred)     │
└────────┬─────────────────────────────────┘
         │ NormalizedListing
         ▼
┌──────────────────────────────────────────┐
│ matching/                                │
│   normalize  brand/model/year extraction │
│   fingerprint  cross-source dedup hash   │
│   score  rapidfuzz + hard gates          │
│   llm_tiebreaker  Anthropic on the band  │
└────────┬─────────────────────────────────┘
         │ ScoredListing
         ▼
┌──────────────────────────────────────────┐
│ SQLAlchemy persistence                   │
│   shops, listings, searches, matches,    │
│   notified_listings, outreach_*, opt_outs│
└────────┬─────────────────────────────────┘
         │
         ▼
┌────────────────────┐   ┌─────────────────────┐
│ notifications/     │   │ outreach/           │
│   email digest     │   │   composer → queue  │
│   (Phase 2)        │   │   sender → inbox →  │
│                    │   │   classifier        │
│                    │   │   (Phase 3)         │
└────────────────────┘   └─────────────────────┘
```

## Why four tiers

| Tier | What it covers | Why this tier exists |
|---|---|---|
| **A** Reverb API | The single largest US guitar marketplace, including 25+ of our seeded shops' storefronts | One API key gives us most of the inventory we care about |
| **B** Shopify `/products.json` + dedicated scrapers | Boutique/vintage shops with their own e-commerce, but readable inventory | Some inventory isn't on Reverb (or has different pricing direct) |
| **C** LLM-assisted generic crawler | Small shops with idiosyncratic sites | Long tail with no API and no pattern match; deferred — Tier B covers most |
| **D** Email/contact-form outreach | Shops with no parseable inventory at all | Last resort. We ask politely if they have it, classify replies |

The original plan assumed Tier B would include dedicated HTML scrapers for the big retailers. Live testing surfaced that Sweetwater/Wildwood/Carter/Elderly all WAF-block direct scrapers. All four also have Reverb storefronts, so we route them through Tier A via `reverb_shop_slug`. The dedicated scraper modules still exist but are dormant.

## Module map

```
src/guitar_searcher/
  cli/                  # Typer entrypoints
    main.py             # root app
    search.py shops.py watch.py outreach.py

  schemas/              # Pydantic v2 contracts (wire/domain)
    query.py            # QuerySpec — single source of truth for "what guitar"
    listing.py          # NormalizedListing — lingua franca every scraper emits
    shop.py             # Shop + InventoryStrategy + ShopClassification enums

  models/               # SQLAlchemy 2.x ORM
    base.py             # DeclarativeBase + TimestampMixin
    shop.py listing.py notifications.py outreach.py

  db/
    session.py          # engine + get_session() context manager
    seed.py             # YAML loader -> ShopRow upsert
    seed_data/major_retailers.yaml  # 30 hand-curated shops

  scrapers/             # Tier A / Tier B adapters
    base.py             # AbstractScraper + ScraperContext
    registry.py         # decorator-based registry (auto-loads modules)
    reverb_api.py       # Tier A
    shopify_generic.py  # generic /products.json
    sweetwater.py wildwood.py carter_vintage.py elderly.py
    _html_search.py     # shared HtmlSearchScraper base (JSON-LD → OG → CSS)

  matching/
    normalize.py        # title → (brand, model, year+confidence, finish)
    fingerprint.py      # SHA-1 cross-source dedup key
    score.py            # rapidfuzz + hard gates → ScoredListing
    llm_tiebreaker.py   # Anthropic structured-output for ambiguous band

  llm/client.py         # Anthropic SDK wrapper, lru_cached

  discovery/            # Phase 2c
    reverb_directory.py # harvest unique shop slugs from listings
    osm.py              # Overpass query for US musical-instruments
    dedupe.py           # fuzzy shop matching (domain | slug | name+city)

  notifications/
    email_digest.py     # SMTP digest of new watch matches

  outreach/             # Phase 3 — Tier D
    compliance.py       # CAN-SPAM helpers + strip_quoted_reply
    composer.py         # template + optional Claude personalization
    queue.py            # eligible-shop selection + draft creation + cooldown
    sender.py           # SMTP send with CAN-SPAM + opt-out gates
    inbox.py            # IMAP poll + Message-ID threading
    classifier.py       # Claude reply classifier (has_it / knows_of / ...)

  scheduler/runner.py   # APScheduler BlockingScheduler — watch cadence daemon

  search_runner.py      # orchestrates scrapers + dedupe + score + persist
  watch_runner.py       # one watch execution: search + diff + notify + record
  config.py             # pydantic-settings (env vars)
  utils/                # logging (structlog), ratelimit (aiolimiter)
```

## Core data contracts (don't change lightly)

- **`QuerySpec`** — `schemas/query.py`. Brand/model/year/finish/price/keywords/exclude/conditions/all-original. Every scraper, matcher, composer, and outreach template reads from this. Stable.
- **`NormalizedListing`** — `schemas/listing.py`. What every scraper emits. The matcher consumes only this. If you add a Tier C/D source, it produces this.
- **`AbstractScraper`** — `scrapers/base.py`. Async `search(query, ctx, shop=None) -> ScraperResult`. New tier? Implement this.

## How a search flows

1. CLI parses args → `QuerySpec`.
2. `search_runner.run_search()` loads active shops, builds task list:
   - Generic scrapers (Reverb API) fire once.
   - Shop-bound scrapers (Shopify-generic, dedicated) fire once per matching shop.
3. Async fan-out under semaphore + per-host rate limiter.
4. All listings deduped by SHA-1 fingerprint; prefer non-Reverb URL on ties.
5. `score_listing(query, listing)` applies hard gates (price/year/exclude/originality), then weighted fuzzy on brand/model/finish/keywords.
6. LLM tiebreaker re-scores the ambiguous 0.45–0.75 band.
7. Persist `SearchRow` + `SearchRunRow` + `MatchRow`s. Print Rich table.

## How a watch flows

1. Scheduler fires `watch.id` job per cadence.
2. `run_watch_async` calls `run_search` with watch's stored QuerySpec.
3. For each match, look up its fingerprint in `notified_listings` for this watch.
4. New matches go to `send_match_digest` → SMTP digest.
5. Record `(search_id, fingerprint)` in `notified_listings` so the same listing never re-notifies.

## How outreach flows

1. `eligible_outreach_shops` filters: active + email present + strategy in {email_only, generic_crawler, none} + not opted out + outside cooldown window.
2. `compose_initial_inquiry` builds a CAN-SPAM-compliant body with optional Claude-personalized opener. Refuses to render without postal address and signer name.
3. Drafts land as `status='draft'`. Cannot send.
4. `approve_draft` flips to `queued`. Records timestamp.
5. `send_outreach_attempt` checks CAN-SPAM + opt-out at send time too (defense in depth). Sets `Message-ID` for reply correlation.
6. `poll_replies` reads IMAP UNSEEN, threads via `In-Reply-To`/`References`, persists raw bodies, marks attempts `replied`.
7. `classify_pending` strips quoted prior conversation, then runs Claude structured-output to bucket into has_it/knows_of/no/unclear/autoresponder/unsubscribe. Auto-records opt-out rows on `unsubscribe`.

## Things that look weird but are correct

- **Hand-written scrapers (sweetwater/wildwood/carter_vintage/elderly) are registered but never run.** They live in the registry but no shop in the seed YAML uses `inventory_strategy=dedicated_scraper` for them. Reason: WAF blocking. Kept in code in case Reverb storefront coverage proves insufficient.
- **`reverb_api` scraper has `is_generic=True`.** It runs once per search regardless of which shop you bind it to. The Reverb API itself searches across all of Reverb; the per-shop `reverb_shop_slug` field in `shops` is informational for future per-shop queries.
- **Settings cache (`get_settings.cache_clear()`) is called in tests.** Pydantic-settings caches the snapshot at first read; tests that change env vars must invalidate it.
