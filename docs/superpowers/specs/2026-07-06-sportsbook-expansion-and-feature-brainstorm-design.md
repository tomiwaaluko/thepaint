# Sportsbook Expansion + Feature Brainstorm — Design

**Date:** 2026-07-06
**Branch:** `claude/railway-feature-brainstorm-vwifyt` (based on `railway`)
**Status:** Awaiting user review — no implementation until approved

## Context

Tha Paint currently ingests betting lines from a single source: The Odds API
(`chalk/ingestion/odds_fetcher.py`), fetching player props + game totals for
`regions: us` once per day inside the 07:00 UTC Railway ingest cron. Lines are
upserted into `betting_lines` keyed on `(game_id, player_id, market, sportsbook)`
— re-fetches **overwrite** the previous line, so no line-movement history exists.
Edge calculation (`chalk/betting/over_under.py`) assumes American over/under
odds and de-vigs them.

The user's stated priority: **add PrizePicks and Hard Rock Bet lines.**

## Part 1 — Hard Rock Bet (small, do first)

### Finding

Hard Rock Bet is already carried by The Odds API under bookmaker key
`hardrockbet`, but it lives in region **`us2`** — the current fetcher only
requests `regions: "us"`, so it never appears in responses.

### Approaches

| | Approach | Trade-offs |
|---|---|---|
| **A (recommended)** | Add `us2` to the `regions` param (`"us,us2"`) | One-line-ish change; also picks up other us2 books (ESPN BET, Ballys, etc.) for free. Cost: The Odds API bills per region × market, so per-event quota usage roughly doubles. |
| B | Use the `bookmakers=hardrockbet` param on a second request | Surgical quota control, but a second request per event and more code paths. |
| C | Filter response to an allowlist of books after fetching `us,us2` | Approach A + a `ODDS_BOOKMAKER_ALLOWLIST` setting; keeps `betting_lines` from bloating with books nobody looks at. |

**Recommendation:** A now, with C's allowlist as a config setting if table
growth or dashboard noise becomes a problem. No schema change needed —
`hardrockbet` rows flow through the existing upsert untouched.

### Notes

- Hard Rock Bet occasionally drops out of the feed during maintenance windows;
  the existing warn-and-continue behavior already handles a missing bookmaker
  gracefully.
- Quota check: current plan's monthly credit budget should be re-estimated
  with 2× region cost before flipping this on in the cron.

## Part 2 — PrizePicks (the real design decision)

### Finding

PrizePicks has **no official public API**. Community projects use the
reverse-engineered endpoint `https://api.prizepicks.com/projections?league_id=7`
(NBA), which returns the full projection board as JSON:API documents. It
requires no key but sits behind Cloudflare — it needs browser-like headers,
polite request rates, and will intermittently return 403s. Paid third-party
scrapers (e.g. Apify's PrizePicks actor) resell the same data with an SLA.

**PrizePicks is not a sportsbook.** It's pick'em DFS: every line is a
projection with fixed payout multipliers by slip type (2-pick Power = 3x,
3-pick = 5x, etc.), not per-line over/under odds. Plus "demon/goblin" lines
carry shifted projections with modified payouts. This changes both the schema
fit and the edge math.

### Approaches

| | Approach | Trade-offs |
|---|---|---|
| **A (recommended)** | New `prizepicks_fetcher.py` hitting the unofficial endpoint directly | Free; one request fetches the whole NBA board (no per-event fan-out). Fragile: Cloudflare 403s, unannounced format changes. Mitigate with realistic headers, existing backoff-with-jitter pattern, and fail-soft (warn + skip step, never fail the cron). |
| B | Paid scraper service (Apify etc.) | Reliable, someone else absorbs breakage. Recurring cost for a personal project; still an unofficial source underneath. |
| C | Defer PrizePicks; Odds API books only | Zero risk, but drops the user's #1 ask. |

**Recommendation:** A, built fail-soft. If Cloudflare blocks become chronic on
Railway's IP range, fall back to B without any schema changes (same data shape).

### Schema fit

Reuse `betting_lines` — no migration needed for the core case:

- `sportsbook = "prizepicks"`, `market` = existing stat keys, `line` = projection.
- `over_odds` / `under_odds` stay `NULL` (already nullable) — pick'em has no per-line odds.
- Demons/goblins: encode in `sportsbook` as `prizepicks_demon` / `prizepicks_goblin`
  (zero-migration), **or** add a nullable `line_flavor` column (cleaner, one
  Alembic migration). Decide at implementation review.

### Edge math for pick'em

`calculate_edge()` compares model probability to de-vigged implied probability
— which doesn't exist for PrizePicks. Instead compare model `over_probability`
to **per-leg breakeven thresholds** derived from the payout tables
(≈54–58% per leg depending on slip type; e.g. 2-pick Power at 3x ⇒
√(1/3) ≈ 57.7%). New small module `chalk/betting/pickem.py`; exact payout
tables encoded as constants at implementation time.

### The killer feature this unlocks

Model p50 vs PrizePicks line, filtered to legs where model probability clears
breakeven — i.e. an automatic **PrizePicks value board** on the dashboard.
That's a differentiated output no plain sportsbook comparison gives you.

## Part 3 — Broader feature brainstorm (ranked)

1. **Line movement history** — the current upsert destroys prior lines. Add a
   `betting_line_snapshots` table (or Timescale hypertable) that INSERTs every
   fetch instead of updating. This is the *prerequisite* for Phase 8's CLV
   tracking, enables opening-vs-closing line features for the models, and
   costs almost nothing now vs. re-backfilling later. Pairs with bumping odds
   fetch cadence (e.g. a second fetch near tip-off for closing lines).
2. **Best-line / line-shopping view** — once ≥3 books are ingested (us + us2),
   a dashboard column showing which book has the softest line per prop, and
   the spread between books (line disagreement is itself an edge signal).
3. **Model accuracy scoreboard** — nightly job grading yesterday's predictions
   vs. actuals vs. the closing Vegas line; rolling MAE and hit-rate by stat on
   the dashboard. Builds trust in the value board and catches model drift.
4. **Edge alerting** — when a prop's edge crosses the "high" tier, push a
   Discord webhook / ntfy notification. Cheap to build on the existing
   `edge_confidence` tiers.
5. **Correlation-aware slip optimizer** — suggest 2–3 leg PrizePicks slips
   accounting for same-game correlation (teammate usage is negatively
   correlated; player pts ↔ game total positively). Genuinely hard; only
   worth it after 1–4 are live.
6. **Kelly-criterion stake sizing** — annotate value-board rows with fractional
   Kelly sizes from model probability + payout. Small utility module.
7. **Strategy backtester** — replay historical predictions against stored
   closing lines to report ROI of "bet every high-edge prop" strategies.
   Depends on #1 accumulating history first.

Deliberately out of scope: live in-game lines (different data tier, different
architecture), additional sports (MLB expansion already has its own track).

## Suggested phasing

| Slice | Contents | Size |
|---|---|---|
| 1 | Hard Rock Bet via `us,us2` + quota check | XS |
| 2 | PrizePicks fetcher (fail-soft) + pick'em breakeven module + value board API/UI | M |
| 3 | `betting_line_snapshots` + closing-line fetch | S |
| 4 | Best-line view + accuracy scoreboard | S–M |
| 5 | Alerting, Kelly sizing, optimizer, backtester | later |

## Open questions for user review

1. Demon/goblin lines: encode in `sportsbook` values (no migration) or a new
   `line_flavor` column (cleaner)? Default plan: `sportsbook` values.
2. Is a paid fallback (Apify ~$/mo) acceptable if the free PrizePicks endpoint
   gets blocked from Railway IPs, or should it fail-soft and go stale?
3. Should slice 3 (line snapshots) ride along with slice 1? It's small and
   every day without it is unrecoverable line-history data lost.
4. NBA is in offseason (crons currently disabled) — build + test everything
   now against MLB markets (`league_id` differs; Odds API sport key
   `baseball_mlb`) so it's proven before the NBA season starts?

## Spec self-review

- No placeholders or TBDs beyond items explicitly deferred to implementation
  (PrizePicks payout table constants, demon/goblin encoding decision).
- No contradiction with CLAUDE.md rules: ingestion stays idempotent
  (snapshots INSERT-only is intentional and documented), async throughout,
  no model/validation changes proposed.
- External facts verified 2026-07-06: `hardrockbet` key + `us2` region on
  The Odds API; PrizePicks unofficial-API status.
