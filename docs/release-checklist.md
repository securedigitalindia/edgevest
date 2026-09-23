# Release Checklist

How to cut and ship an EdgeVest release — versioning convention, backend
steps, frontend steps, and the current outstanding items as of the last time
this doc was updated (see the newest "Status as of" section below — currently 2026-09-22, `v7.7.0`, unreleased).

## Branching model

- **Current (solo)**: everything happens directly on `dev`; tags (`v3.0`
  through `v5.1`) were placed there, and `main` was intentionally left
  untouched at the initial monorepo commit.
- **As of `v5.2` (2026-08-26)**: `main` was fast-forwarded to match `dev`
  (`git merge dev --ff-only`, clean — `main` had never diverged) as the first
  step of moving to a real branching model for when more than one person is
  contributing: new work branches off `main`, PRs into `dev`, and once a
  batch of work on `dev` is ready to ship, `dev` merges into `main` (fast-
  forward, same as this one, as long as nothing lands on `main` directly in
  between) — **`main` becomes the source of truth, and release tags move to
  `main` going forward** instead of `dev`.
- Until other contributors are actually opening PRs against `dev`, this is
  functionally the same solo workflow as before, just with the extra step of
  fast-forwarding `main` at release time instead of never touching it.

## Versioning

- Tags are placed on `main` (`v5.2` on) — `dev` is where work lands first;
  `main` is fast-forwarded to `dev` at release time and the tag goes on
  `main`. (Tags before `v5.2` — `v3.0` through `v5.1` — were placed on `dev`,
  back when `main` was never touched; see Branching model above.)
- Bump both of these together, in their own commit, before tagging:
  - `frontend/package.json` + `frontend/package-lock.json` (`"version"` field,
    top of the file and the `packages[""]` entry — **do not** blind
    find-and-replace the version string across the whole lockfile, other
    dependencies legitimately share version numbers with the app)
  - `backend/server.py`'s `APP_VERSION` constant (added in `v5.0`; no other
    version tracking exists in the backend)
- Tag only when you're about to actually ship — don't chase a tag for every
  commit. `git describe --tags --always --dirty` (used as the default
  release id by `frontend/deploy/deploy.sh`) will honestly report
  `v5.0-1-gabc1234` for anything committed after the tag; that's correct
  behavior, not a bug to fix.
- A tag that has already been pushed should not be force-moved — cut a new
  tag (`v5.0.1`, `v5.1`, ...) instead.

## Backend release (EC2)

1. **Get the code onto the box** — `git pull` (or checkout the release tag)
   at `/home/ubuntu/edgevest`.
2. **Install Python dependencies** — `source venv/bin/activate && pip install
   -r requirements.txt`. `backend/edgevest-web` (the systemd `ExecStart`
   script) only activates the venv and runs gunicorn; nothing installs
   packages automatically. `razorpay>=1.4.0` was added to
   `requirements.txt` alongside the payments module — if prod's venv was set
   up before that, it won't have it yet.
3. **Sync `backend/.env.production`** — this file is gitignored, so the copy
   on a dev laptop and the copy on EC2 are two independent files that never
   auto-sync. Diff and merge by hand; never overwrite the server's copy
   wholesale (it may hold entries — e.g. `CORS_ORIGINS` — that a laptop's
   copy doesn't).
   - Give prod its own `PAYMENTS_CRON_SECRET`, distinct from dev's. Generate
     one with `python3 -c "import secrets; print(secrets.token_hex(24))"`.
4. **Migrate the database** — `python poller.py init`. This is the only
   command in this codebase that touches schema (`db/init_db.py`'s
   `init_db()`, `CREATE TABLE IF NOT EXISTS` everywhere — idempotent, safe to
   rerun, never touches existing data). `python poller.py sync` does **not**
   do this — that command runs `sync/daily_sync.py`'s end-of-day
   candle sync and never calls `init_db()`. Needed at least once for the
   `payment_orders` table, introduced by the Razorpay integration.
5. **Set up the reconciliation cron**, if not already present — nothing in
   this repo schedules `POST /api/payments/reconcile` (confirmed by grepping
   the repo for it — no crontab/systemd-timer file exists anywhere). Add one:
   ```
   */15 * * * * curl -s -X POST -H "X-Cron-Secret: <PAYMENTS_CRON_SECRET>" https://api.edgevest.in/api/payments/reconcile
   ```
   Keep the interval longer than a single run can take — there's no lock
   against two overlapping runs both racing to resolve the same stale order
   (see `docs/architecture.md`'s payments section).
6. **Restart the service** — `sudo systemctl restart edgevest-web`.
7. **Verify** — hit `/api/me` (or similar) and confirm the new code is
   actually serving. Since `RAZORPAY_KEY_ID` is a live key (`rzp_live_...`),
   plan a small real-money checkout smoke test rather than assuming
   test-mode behavior carries over.

## Frontend release (S3 + CloudFront)

Use `frontend/deploy/deploy.sh` — versioned releases, fast rollback. See the
script's own header comment for full mechanics; summary:

```
frontend/deploy/deploy.sh deploy   <prod|staging|dev> [release-id]
frontend/deploy/deploy.sh rollback <prod|staging|dev> <release-id>
frontend/deploy/deploy.sh list     <prod|staging|dev>
frontend/deploy/deploy.sh current  <prod|staging|dev>
```

- Each deploy builds (`npm run build` / `build:staging` / `build:dev`),
  uploads `dist/` to `s3://<bucket>/releases/<release-id>/`, then repoints
  that environment's CloudFront `OriginPath` at the new prefix and
  invalidates `/*`. Nothing previously deployed is touched, so rollback is
  just repointing `OriginPath` at an older release — no rebuild, no
  reupload.
- `release-id` defaults to `git describe --tags --always --dirty`. Pass one
  explicitly (e.g. the tag name) when you want the S3 folder to read cleanly
  as an exact release rather than "N commits past a tag".
- Requires `aws` CLI (profile `default`) and `python3`; does not require
  `jq`.

## Order of operations for a full release

1. Bump versions, commit on `dev` (see Versioning above).
2. Fast-forward `main` to `dev` (`git checkout main && git merge dev --ff-only`),
   tag `main`, push `main` + `dev` + the tag to origin.
3. Backend steps 1–7 above, on EC2, for prod.
4. `frontend/deploy/deploy.sh deploy prod <tag>`.
5. Smoke test prod end-to-end (login, a real small checkout, positions,
   games).

Dev and staging can go through step 4 independently, any time, without
waiting on the backend/prod steps — they're lower-stakes and don't share
prod's Razorpay keys or DB.

## Status as of 2026-09-23 (`v7.7.14` — patch on top of `v7.7.13`, backend-only)

The real fix behind the wrong-value bug `v7.7.13` didn't fully address: Upstox's Historical Candle API
(`get_historical_candles()`, all `bootstrap/upstox_loader.py`/`sync/daily_sync.py` ever used) is
documented to **never** return the current trading day, confirmed live 6+ hours after close — not a
publish delay, a hard API boundary. Upstox has a separate **Intraday Candle Data V3 API**
(`get_intra_day_candle_data`, already in the installed SDK, never called before) specifically for this.
`sync/daily_sync.py`'s `sync_symbol()` now calls both: `fetch_historical()` for everything older than
today (unchanged), new `fetch_intraday()` for today specifically (`1m`/`5m`/`15m`/`1h`/`1d` — no
`weeks`/`months` unit on that endpoint). Verified end-to-end against a temp copy of real prod data:
`candles_1d` went from missing today's row entirely to having the exact correct
`open=23352.15, close=23446.80`. No games-specific code needed — `get_candles(..., "1d", limit=1)` just
works correctly same-day now, benefiting every consumer (games, monthly report, strategies).

Also includes `backend/scripts/correct_2026_09_23_games.py` — a **one-off** correction for the two
2026-09-23 games that had already resolved against wrong data before this fix. Found a real, previously
unpaid winner: user 8 should have won game #6 (close-prediction) by 5.8 points under the real close, but
the game resolved against a stale value with no winner. **Must be run manually on prod** (dry-run first,
then `--apply`) — not something this deploy does automatically, since it touches real user credits.
Delete the script after running it once; the root cause is fixed, this shouldn't recur.

**Needs a poller restart** (picks up the new sync logic) **and `python poller.py sync`** run once
manually if you want today's data backfilled immediately rather than waiting for the next 16:00 cycle.
No new migration.

## Status as of 2026-09-23 (`v7.7.13` — patch on top of `v7.7.12`, backend-only)

Both daily NIFTY games' entry cutoffs now close 15min *before* the real moment they're protecting
instead of exactly at it — `GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST` = 09:00 (was implicitly tied to
`MARKET_OPEN_IST`'s 09:15), `GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST` = 15:00 (was briefly 15:15 exact).
Closing exactly at the answer-determining instant still allows a last-second snipe once the answer is
effectively already known. Required a genuinely new hook point for the open side — `run_live()` now
calls the poller's long-unused `_wait_until()` helper at 09:00, before `wait_for_market_open()`.

**Needs a poller restart only.** No new migration, no frontend deploy.

## Status as of 2026-09-23 (`v7.7.12` — patch on top of `v7.7.11`, frontend-only)

Two more Games UI fixes found while dogfooding the new NIFTY open-prediction game:

- `PredictionGame`'s copy ("Predicted close for NIFTY50", "Actual close", "Where will it close on...")
  was hardcoded for the close-only assumption `price_prediction` used to be safe to make — the
  open-prediction game literally said "close" everywhere. Now derived from the game's title
  (`/open/i.test(game.title)`), same convention the automation uses to name its own games.
- `AdminActions`' manual "Close Game" / "Resolve & Award Credits" buttons are now hidden for any
  `auto_kind` game — clicking either would have fought the automation (closing entries early, or
  resolving without the `win_threshold` payout rule this screen's resolve action never applies).

Frontend deploy only — no backend/DB change.

## Status as of 2026-09-23 (`v7.7.11` — patch on top of `v7.7.10`, frontend-only)

Fixed `Games.jsx`/`GameDetail.jsx` each having their own broken local `fmtIst()` (backwards
`Z`-handling meant `new Date(...)` parsed timestamps in the machine's own local timezone instead of
UTC — showed the wrong wall-clock time, e.g. "10:00 am" for a value that meant 3:30 pm IST, on any
non-UTC machine). Replaced with the shared, correctly-written `fmtIstShort()` (`utils/format.js`) used
everywhere else in the app; also fixed the same bug pattern in the `v7.7.10`-era edit form's
`utcToLocalInput`/`localInputToUtc`. Frontend deploy only — no backend/DB change.

## Status as of 2026-09-23 (`v7.7.10` — patch on top of `v7.7.9`, backend-only)

Redesigned the daily NIFTY prediction games (`docs/prd/nifty-daily-prediction-games.md`): both games now
resolve together at the 16:00 EOD sync, from one shared `candles_1d` fetch, instead of resolving the
open-game immediately at 09:15 from an approximate live-LTP snapshot — `candles_1d`'s official `open`
column doesn't exist before that same sync anyway. Entries still close promptly (09:15 for open, 15:00
for close, `GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST`). New `get_closed_auto_game()` alongside
`get_active_auto_game()`. Manual CLI trigger split: `poller.py games open|cutoff|eod` (was `open|close`).

**Needs a poller restart only** (no `poller.py init` — no schema change this time, `auto_kind` already
added in `v7.7.8`) — picks up the new 3-hook-point lifecycle.

## Status as of 2026-09-22 (`v7.7.9` — patch on top of `v7.7.8`, backend-only)

Chain-trigger threshold tuning, applied directly on prod by the user and synced back into this repo:
`NIFTY_CE_ITM400/200/100/0_RATIO_DIAG_1X2` tightened (`max_debit_pts` 25 → 10/20/15/10 respectively;
`ITM300` unchanged at 25), and a new `NIFTY_CE_OTM200_RATIO_DIAG_1X2` trigger added (`min_credit_pts=10`,
same family as the existing `OTM100` credit-rule trigger). No schema/code change — `config.CHAIN_TRIGGERS`
only. Also folds in the "Manual trigger" doc section for `poller.py games open|close` that was missed
in the `v7.7.8` commit.

Needs a poller restart only (no `poller.py init`, no frontend deploy) — picks up the new trigger list.

## Status as of 2026-09-22 (`v7.7.8` — patch on top of `v7.7.7`, backend-only)

New feature, not a bug fix: two daily `price_prediction` games (NIFTY open/close, one winner each,
paid only within a points threshold) now run fully automated inside the poller — no admin click, no
new cron/systemd unit. Also fixed a related latent bug found while building this: `wait_for_market_open()`
only ever checked time-of-day, never day-of-week (safe so far only because the process happens to
already be idling there when a weekend rolls past). Full design: `docs/prd/nifty-daily-prediction-games.md`.

**Needs `python poller.py init` again** — adds the new `games.auto_kind` column. Restart the poller
(picks up the new hook points + the `wait_for_market_open()` fix). No frontend change (the existing
Games UI already renders/enters/resolves `price_prediction` games generically) and no `edgevest-web`
restart strictly required, but bump/deploy both per the usual convention since `config.py`/`db/queries.py`
changed either way.

## Status as of 2026-09-22 (`v7.7.5` — patch on top of `v7.7.4`, backend-only)

Real prod bug, found from a `journalctl` excerpt the user shared: `chain_triggers.run_chain_triggers()`
ran inline in the poller's main loop, before the LTP fetch/tick recording — a slow evaluation cycle
(~2 min, observed before the v7.7.3/v7.7.4 speed fixes) froze the *entire* poller for that long. No
price polls, no ticks, no candles, visible as "only 0 tick(s) — skipped" on the next candle close.
The speed fixes reduce how often this happens but don't eliminate the structural risk. Fixed:
`run_chain_triggers()` now runs in a background daemon thread (`live/poller.py`), started but never
waited on; an overlapping cycle is skipped (logged) rather than stacked. Verified: guard-and-skip
logic in isolation, and the real evaluator run end-to-end from an actual background thread.

No new migration. Needs a poller restart only (no `poller.py init`, no frontend deploy).

## Status as of 2026-09-22 (`v7.7.4` — patch on top of `v7.7.3`, backend-only)

The futures-price dedup in `v7.7.3` wasn't the real bottleneck. Each of the 7 triggers was also
independently calling `get_merged_cadence_dates()` on every cycle — measured at ~4.1s/call on the
real 1.95M-row `option_chain_5m` table (no index covered `expiry_type`, so it fell back to a full
symbol scan). 7 calls/cycle cost ~29s. Fixed:
- New index `idx_option_chain_5m_sym_type_expiry` (`db/init_db.py`) — cuts the query to ~2.9s/call
  and speeds up every other caller of `get_merged_cadence_dates()`, not just the triggers.
- `run_chain_triggers()` now fetches the snapshot timestamp once (global) and the expiry list once
  per symbol, passing both into every evaluator instead of each fetching its own.

Measured end-to-end: `run_chain_triggers()` ~29-30s/cycle → ~4.2s/cycle. Every trigger's logged
credit/debit unchanged; draft creation and the Telegram alert re-verified working.

**Needs `python poller.py init` again** — creates the new index this time, not just
`chain_trigger_fires`. Without it the code still works but the query stays slow. Poller restart
required; no frontend change (version bumped anyway per this repo's "bump both together" convention).

## Status as of 2026-09-22 (`v7.7.3` — patch on top of `v7.7.2`)

- **Backend:** `run_chain_triggers()` now fetches the front-month futures price once per distinct
  symbol per 5-min cycle, shared across every trigger on that symbol, instead of each of the 7
  triggers fetching it independently (7 live Upstox calls -> 1). No behavior change — verified
  every trigger's logged credit/debit is unchanged.
- **Frontend:** every recommendation card on the Trades page now shows `#<display_code> (<note>)`
  in the adjustment-count strip, not just the bare code — makes a trigger-generated draft's
  description (strikes/expiries/credit-debit) visible without scrolling to the card title.

Needs backend + poller restart (for the dedup fix) and a frontend deploy (for the UI change).

## Status as of 2026-09-22 (`v7.7.2` — patch on top of `v7.7.1`)

`v7.7.1` shipped the corrected 6-trigger CE calendar/diagonal sweep. This patch adds:
- A 7th trigger, `NIFTY_PE_RATIO_DIAG_4LEG_400` — the 4-leg 1:2:1:2 PE ratio diagonal (same
  shape as `docs/prd/pe-ratio-diagonal-strategy.md`), wired up as a live auto-draft trigger for
  the first time. Fires on `credit > 5`; real data prices it as a debit under normal conditions,
  so — like several of the CE triggers — it's expected to fire rarely.
- All 7 trigger names made consistent: CE ones renamed `..._DIAG_1X2` → `..._RATIO_DIAG_1X2`;
  PE renamed `NIFTY_PE_RATIO_DIAG_400` → `NIFTY_PE_RATIO_DIAG_4LEG_400`.
- Every evaluation now logs its computed credit/debit and whether the rule was met, **whether or
  not it fires** — previously only a fire printed anything, so there was no way to see how close a
  trigger was on a normal 5-min cycle.
- `NIFTY_CE_OTM100_RATIO_DIAG_1X2` given its own `credit > 5` rule (confirmed with the user),
  diverging from the other five CE triggers which stay on `debit < 25`. On the reference snapshot
  this means OTM100 no longer fires (14.1pt debit clears the old rule but not this one).
- Trigger threshold config (`max_debit_pts`/`min_credit_pts`) has no default any more — every
  `CHAIN_TRIGGERS` entry must state its own rule explicitly, or `config.py` raises at import time.

Needs the same deploy steps as `v7.7.1` (backend/poller pull + restart; no frontend change, no DB
migration beyond what `v7.7.1` already required).

## Status as of 2026-09-22 (`v7.7.0` — committed on local `main`, NOT yet tagged, pushed or deployed)

Nothing below has been shipped. `main` is 10 commits past `v7.6.3` (`0912c0c`), all local. Bumped to
`7.7.0` in `frontend/package.json` + lockfile and `backend/server.py`'s `APP_VERSION` (which had been
left at `7.5.0` through the 7.6.x bumps — now back in sync). Not tagged: tag only when about to ship.

**What is in this release**

- **Fixes**: exited-trade realized P&L now sums every leg row, so a leg closed by an adjustment is no
  longer dropped (#SEP26-2: +11,245 → −3,282.5; Sept monthly total 30,584 → 16,056.5; no other trade or
  month changes); trade display codes use MAX+1 so a deleted trade no longer causes duplicates; the
  exited card shows the entry margin and computes ROI on it (was the gross `margin_required`).
- **Strategies**: second provider `pe_ce_ratio_spread_1x2` (weekly 1:2 calendar ratio on PE/CE — see
  `docs/prd/pe-ce-ratio-spread-1x2.md`) and a list → detail Strategies UI (`/profile/strategies`,
  `/profile/strategies/:id`); settle-once cache keys are versioned; config mutation awaits its refetch.
- **Triggers & alerts**: every per-tick alert trigger removed (`TRIGGERS = []`; the poller still polls
  every `SYMBOLS` entry). New option-chain triggers (`CHAIN_TRIGGERS`, one shared
  `_calendar_ratio_trigger()` template): 6 entries sweeping `itm_points` 400/300/200/100/0/-100
  (`NIFTY_CE_ITM400_RATIO_DIAG_1X2` through `NIFTY_CE_OTM100_RATIO_DIAG_1X2`, ITM 400 down to OTM 100) — 1:2 CE
  diagonal, 400pt gap between strikes; ITM400 through ITM0 fire on `debit < 25`, OTM100 fires on its own
  `credit > 5` rule. Each creates a DRAFT trade and sends a
  Telegram "Trigger Fired" alert stating whether a draft is linked
  (`docs/prd/option-chain-calendar-ratio-trigger.md`). Removed Telegram messages: morning brief,
  08:30 pre-market analysis, EOD brief, account-level entry/exit/auto-exit. Still sent: New Trade,
  New Adjustment, Trade Exited, Trigger Fired.

**Deploy steps specific to this release (in order)**

1. Backend on EC2: `git pull` / checkout the tag; no new Python dependencies.
2. **`python poller.py init`** — creates the new `chain_trigger_fires` table. Required: without it the
   triggers can never record a fire, so they never create a draft.
3. One-off SQL against the prod DB (back it up first) to fix the existing duplicate display code —
   verify trade ids 54/55 still match before running:
   ```sql
   UPDATE recommended_trades SET display_code = 'SEP26-9'
   WHERE id = 55 AND display_code = 'SEP26-10'
     AND NOT EXISTS (SELECT 1 FROM recommended_trades WHERE display_code = 'SEP26-9');
   -- expect 1 row changed
   ```
4. Restart **both** `edgevest-web` (new routes/provider, P&L, margin field) **and the poller**
   (empty `TRIGGERS`, chain triggers, removed briefs). Restart the poller before 09:15 IST on a trading day.
5. `frontend/deploy/deploy.sh deploy prod v7.7.0` (after tagging).

**Post-deploy checks**

- `/api/strategies` returns both providers (401 unauthenticated is healthy, 404 means the blueprint did
  not register); open `#SEP26-2` on Trades — exit prices on every leg, realized −₹3,283 (−3.0%).
- The poller log shows `[no triggers — data collection only]` for NIFTY50/BANKNIFTY/RELIANCE and
  `option_chain_capture` lines every 5 min.
- Do **not** expect a draft every morning — both the debit and credit conditions are genuinely
  data-dependent, not almost-always-true. On the 2026-09-21 close snapshot none of the seven triggers
  would have fired (OTM100's 14.1pt debit clears its old `debit < 25` rule but not its current
  `credit > 5` rule — a debit is never a credit). A quiet first morning is expected, not a bug — every
  evaluation now logs its own credit/debit and whether the rule was met, fire or not, so check the
  poller log for `[chain_triggers]` lines to see exactly where each trigger stands.
  Drafts are silent until published.

**Known / not part of this release**

- `wip/zerodha-broker-execution` (Zerodha broker execution, unmerged) will conflict with `main` in
  `backend/db/queries.py` when merged; other files auto-merge.
- The Telegram bot token and chat id are hardcoded in `backend/config.py` — move to an env file and
  rotate the token.
- The near-leg exit/roll of any published trigger draft is manual; no risk/margin is computed for a
  draft until publish.

## Status as of 2026-09-09 (`v7.6.0` — frontend and backend both released to prod)

- ✅ `main` tagged `v7.6.0` (commit `afaa7f5`) and pushed to origin, along
  with the tag. This release adds: admin Strategies dashboard
  (`/profile/strategies`, new `backend/strategies/` package) — an on-demand,
  native view of the PE+CE ratio diagonal strategy's backtest state (a
  settle-once window cache keyed on a params fingerprint so only the
  still-open window ever recomputes; config split into strategy-shape
  params — `leg_gap`/`strike_multiple`/`initial_gap`/`side` — versus a
  separate, extensible `trigger` sub-object; each triggered set now reports
  its own exit debit vs current debit), replacing the manual
  CLI-run-then-republish-artifact workflow. New tables:
  `strategy_backtest_windows`, `strategy_configs`. Also reduces
  `option_chain_5m` capture from 15 to 9 Upstox calls per 5-min snapshot
  (per-type expiry rank depth — weekly 0-3, monthly 0-2, quarterly 0-1 —
  instead of one shared 0-4 depth for all three).
- ✅ `edgevest.in`/`www.edgevest.in` — serving `releases/v7.6.0` (deployed via
  `frontend/deploy/deploy.sh deploy prod v7.6.0` from this session, release-id
  pinned explicitly since the working tree had an unrelated dirty file at
  deploy time; CloudFront invalidation `I295AOMAKWC6QOUQFA5L9C3FU1` issued —
  allow a few minutes for edges to catch up. Previous release `v7.5.0` still
  sits untouched in S3 for instant rollback). `dev.edgevest.in`/
  `staging.edgevest.in` were last deployed further back and will read as
  behind until someone runs `deploy.sh deploy dev v7.6.0` /
  `deploy.sh deploy staging v7.6.0`.
- ✅ Prod backend (EC2) released to `v7.6.0` by the user directly (backend is
  never run from inside a Claude Code session — see root `CLAUDE.md`):
  `poller.py init` run (creates the two new tables above) and the
  `edgevest-web` service restarted to pick up `server.py`'s new
  `backend/strategies/` blueprint registration. Restart took a little longer
  than usual, per the user — came back up, not independently confirmed via
  `/api/strategies` from this session; worth a quick check if anything looks
  off (401 unauthenticated is the healthy response, 404 would mean the
  blueprint didn't register).
- ⚠️ `main`/`dev` divergence (called out in earlier status notes) is
  unchanged this release — work continues to land directly on `main`. Still
  worth formally deciding whether to retire `dev` or resume the documented
  branching model.
- Dependabot: GitHub reported **5 vulnerabilities (2 high, 3 moderate)** on
  the default branch as of this push (2026-09-09) — check
  `https://github.com/securedigitalindia/edgevest/security/dependabot` for
  current detail; not investigated or fixed as part of this release (this
  release's own dependency change was net-negative in count — recharts was
  added then fully removed again in the same session).
