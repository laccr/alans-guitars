# Runbook

Common workflows. Every command assumes you're in the project root with `.venv` activated.

## First-time setup on a fresh machine

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Copy template -> real config, then edit .env with real values
cp .env.example .env
# Edit .env. Required at minimum: REVERB_TOKEN, ANTHROPIC_API_KEY.
# For watches: GS_NOTIFY_FROM/TO + GS_SMTP_* (Gmail: use an App Password).
# For outreach: GS_OUTREACH_PHYSICAL_ADDRESS (CAN-SPAM), GS_OUTREACH_SIGNER_NAME, GS_IMAP_*.

# Apply schema, seed the hand-curated shop list
alembic upgrade head
guitar-searcher shops seed
```

NOTE: `.env` is gitignored. `.env.example` is committed. Real secrets ONLY belong in `.env`.

## Search for a guitar

```powershell
guitar-searcher search --brand Fender --model Jaguar `
    --year-min 1962 --year-max 1965 `
    --finish sunburst --max-price 25000

# Useful flags
#   --no-llm           skip the Anthropic tiebreaker on ambiguous matches
#   --min-score 0.5    raise the cutoff
#   --limit 10         show only top N
#   --no-save          run-only; don't persist a search_run
#   --condition used --condition very_good   (repeatable)
#   --must-have hardtail  --exclude refin    (repeatable)
#   --all-original-only   reject reissues/partscasters/refins
```

## Grow the shop directory

```powershell
# Reverb directory (works): walks broad listings queries, harvests US shop slugs
guitar-searcher shops discover --source reverb --max 200

# OSM Overpass (intermittent; public infra has been flaky)
guitar-searcher shops discover --source osm

# Manually add a shop you found
guitar-searcher shops add --name "Some Shop" --domain someshop.com `
    --email contact@someshop.com --city Nashville --state TN `
    --tz America/Chicago --strategy email_only

guitar-searcher shops list --all    # --active by default; --all shows inactive
```

## Saved watches with email notifications

```powershell
# Create a watch
guitar-searcher watch add --name "pre-CBS strat" `
    --cadence daily `
    --brand Fender --model Stratocaster --year-min 1960 --year-max 1965 `
    --finish sunburst --max-price 40000

guitar-searcher watch list
guitar-searcher watch run 1          # one-off (still respects notified-dedup)
guitar-searcher watch run-all
guitar-searcher watch disable 1
guitar-searcher watch enable 1
guitar-searcher watch remove 1

# Long-running daemon: re-runs each active watch on its cadence
guitar-searcher watch schedule
```

Cadences: `hourly` (every hour at :05), `daily` (07:15 UTC), `weekly` (Mondays 07:15 UTC). New matches that haven't been notified before for this watch trigger a Rich-HTML email digest to `GS_NOTIFY_TO`.

## Outreach to non-Reverb shops (Phase 3)

```powershell
# Verify config (CAN-SPAM, SMTP, IMAP)
guitar-searcher outreach check

# Draft inquiries for shops eligible for outreach (email_only/none/generic_crawler strategies)
guitar-searcher outreach draft --brand Fender --model Jaguar --max-price 25000

# Inspect what was generated
guitar-searcher outreach review                # all drafts
guitar-searcher outreach show 3                # full body of attempt #3

# Approve before any send (sending a draft outright is refused)
guitar-searcher outreach approve 3
guitar-searcher outreach approve --all

# Dry-run first; then real send
guitar-searcher outreach send --dry-run
guitar-searcher outreach send

# Pull replies from IMAP and classify them via Claude
guitar-searcher outreach poll

# Aggregate counts
guitar-searcher outreach status
```

Reply classifications produced by the Claude classifier:
`has_it | knows_of | no | unclear | autoresponder | unsubscribe`.

When a reply classifies as `unsubscribe`, an `opt_outs` row is inserted automatically and the shop is permanently excluded from future outreach.

## Operating the scheduler as a background service

For now, `guitar-searcher watch schedule` runs in the foreground. Options:

1. Run it in a separate PowerShell tab and leave it open.
2. Wrap it in NSSM or Windows Task Scheduler for auto-start on boot.
3. (Future) consider running the scheduler under systemd / a Windows service if you move to a VPS.

## Reset / nuke

```powershell
# Drop and recreate the schema (DESTRUCTIVE)
Remove-Item guitar_searcher.db
alembic upgrade head
guitar-searcher shops seed
```

## Common gotchas

- **Windows terminal can't render some Unicode** (em-dash, narrow-no-break-space). All user-facing strings have been ASCIIfied where they appear in CLI output, but raw email bodies may contain Unicode — use `Read` on `reply_dump.txt` or open in an editor instead of printing.
- **Gmail App Password vs regular password** — always use an App Password generated at `myaccount.google.com/apppasswords`. Regular password will be rejected.
- **`.env.example` is the template, `.env` is real.** Putting secrets in `.env.example` will commit them. There's a banner at the top of `.env.example` to remind you.
- **Tests run against a temp SQLite per test** via the `tmp_db` fixture — they do not touch your real `guitar_searcher.db`.
