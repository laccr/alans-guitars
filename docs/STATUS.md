# Project Status

_Last meaningful update: 2026-05-23 after Phase 3 fixes (`de6dae5`)._

## TL;DR

Phases 1, 2, 2b, 2c, 3 are merged on `main`. Live-validated end to end:

- **Search** (Tier A Reverb + Tier B Shopify): returns hundreds of real matches in <60s.
- **Discovery** (Reverb directory): grew the shop directory from 30 hand-curated to 46 shops.
- **Watches**: SMTP digest delivers to `troy@littlestudybuddy.com` on new matches.
- **Outreach** (Tier D): compose -> approve -> SMTP send -> IMAP poll -> threading -> LLM classify. A real reply was correctly classified `knows_of` after the quote-stripping fix.

## What works today

| Capability | Command | Notes |
|---|---|---|
| Run one-off search | `guitar-searcher search --brand <...>` | Hits Reverb API + Shopify-pattern shops. Persists results. |
| Manage shop directory | `guitar-searcher shops {seed,list,add,discover}` | `discover --source reverb` works. `--source osm` blocked by Overpass server issues. |
| Saved watches + notifications | `guitar-searcher watch {add,list,run,run-all,schedule}` | `schedule` is the long-running APScheduler daemon. |
| Outreach to non-Reverb shops | `guitar-searcher outreach {check,draft,review,show,approve,send,poll,status}` | CAN-SPAM compliance gated on `GS_OUTREACH_PHYSICAL_ADDRESS`. |

## What's blocked / partial

1. **OSM Overpass discovery.** Public Overpass infrastructure returned 406 on every endpoint from this network. Code is in place with a 5-endpoint fallback chain; retry from another network or wait for the public servers to recover. See `discovery/osm.py`.
2. **Hand-written HTML scrapers (Sweetwater, Wildwood, Carter Vintage, Elderly).** All four sites WAF-block scrapers. Their modules still exist in `scrapers/` but the seed YAML routes those shops via `inventory_strategy=reverb_api` and the corresponding Reverb storefronts. The HTML scrapers are dormant; revive only if Reverb storefront coverage proves insufficient.
3. **Outreach has no live candidates yet.** The 4 vintage shops marked `email_only` in the seed (Norman's Rare, Retrofret, Killer Vintage, Songbirds) are inactive and missing email addresses. Either hand-curate emails for them, or wait for OSM discovery to seed contact-rich shops.

## DB state (after cleanup of Phase 3 self-test)

- 46 shops (30 hand-curated + 16 discovered from Reverb directory). 38 active.
- 0 outreach_attempts, 0 outreach_replies, 0 opt_outs (test artifacts cleaned up).
- 0 saved watches (one test watch was created during Phase 2 verification and removed).
- 4 Alembic migrations applied:
  - `20260522_0000` initial schema
  - `20260523_0100` notified_listings (watch dedup)
  - `20260523_0200` shops.discovered_from + last_verified_at
  - `20260523_0300` outreach_attempts + outreach_replies + opt_outs

## Test + lint posture

```
78 tests passing
mypy --strict   : clean
ruff check      : clean
alembic upgrade : clean
```

## Roadmap remaining

| Phase | Status | Notes |
|---|---|---|
| 1 — MVP | done | |
| 2 — Watches + notifications | done | SMTP via Gmail App Password. |
| 2b — Direct scraper revival | deferred | Only worth pursuing if Reverb storefront coverage gaps emerge. |
| 2c — Shop discovery | done (Reverb) / blocked (OSM) | Google Places not implemented; deferred to budget approval. |
| 3 — Email outreach | done | Awaiting real candidate shops. |
| 4 — Opt-in AI voice calls | not started | Significant build + ongoing per-minute cost. Requires Twilio + ElevenLabs or OpenAI Realtime setup. FCC AI disclosure required as turn 1 of every call. |
| 5 — Web UI | not started | Only needed if CLI feels limiting. |
