# Daily NIFTY open/close prediction games — fully automated

**Status:** built 2026-09-22. Reuses the existing `price_prediction` game type end-to-end (schema,
`/api/games*` routes, frontend create/enter/resolve UI — none of it changed); the only new thing is
automation inside `live/poller.py` that runs the two games' full lifecycle without any admin click.

## What it does

Two `price_prediction` games run every trading day. Entries close promptly for each, but **neither is
resolved until the 16:00 EOD sync** — see "Why both resolve at EOD" below.

1. **"Predict NIFTY's Open — `<date>`"** — created at EOD the evening before, for whichever day is the
   next actual trading day (`holidays.next_trading_day()` — skips weekends/holidays, so a Friday's EOD
   can jump straight to the following Monday, or further over a long weekend). Entries close at 09:00
   (`GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST`) — a 15min safety margin *before* market open (09:15), not the
   market-open moment itself, so nobody can lock in a guess once NIFTY has effectively already started
   printing. Not graded until EOD.
2. **"Predict NIFTY's Close — `<date>`"** — created the moment the open-game's entries close (09:00,
   same instant, same function call), for *today*. Entries close at 15:00
   (`GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST`) — a 15min safety margin before NIFTY's real/effective close
   (15:15, confirmed by the user — **not** `MARKET_CLOSE_IST`'s 15:30). Also not graded until EOD.

Both cutoffs are deliberately *before* the moment they're protecting, not exactly at it — the whole
point of a cutoff is to stop a near-certain last-second entry once the answer is effectively already
known, and a cutoff set exactly at that moment doesn't actually prevent that.

Both are resolved together at 16:00, immediately followed by creating the next open-game.

Every title/description always states the target date explicitly (user requirement — these run daily,
so "Predict NIFTY's Close" alone would be ambiguous about which day on the games list).

## Why both resolve at EOD, not as soon as their entries close

First version resolved the open-game immediately at 09:15, using that tick's live LTP as "the actual
open". User caught the inconsistency: the close-game already waits for the EOD sync's *official*
`candles_1d` close rather than an approximate live snapshot — the open-game should get the same
treatment, using `candles_1d`'s `open` column. The catch: **that column doesn't exist until the exact
same 16:00 sync** — there's no earlier "official open" published anywhere in this system's pipeline.
So resolving the open-game accurately necessarily means resolving it at EOD too, same as the close-game
— entries still lock promptly (09:00 for open, 15:00 for close), only the grading/payout is deferred
to when real data exists. Both games are graded from **one shared `candles_1d` row fetch** at EOD, so
they're always consistent with each other and with the same sync that produces every other candle in
this system.

**Entry-cutoff times went through two corrections on 2026-09-23, ending at a safety-margin design:**
1. First built as 15:00 for the close-game (a 30-minute-before-close guess, `MARKET_CLOSE_IST` minus an
   arbitrary buffer), open-game entries closing exactly at market-open (09:15).
2. User corrected the close-game's *reference point*: NIFTY's real/effective close happens at 15:15,
   not 15:30 — so `GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST` briefly became `(15, 15)` (exactly at the real
   close, no margin).
3. **Final correction:** entries closing *exactly at* the answer-determining moment still lets someone
   lock in a near-certain last-second guess right as the poller notices the cutoff. User: build in a
   15min safety margin on both sides instead — `GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST = (9, 0)` (15min before
   the 09:15 open) and `GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST = (15, 0)` (15min before NIFTY's real 15:15
   close). This is a genuinely new hook point for the open side — previously the open-game's entries
   closed implicitly, tied to `wait_for_market_open()` returning; now `run_live()` calls the
   already-existing-but-previously-unused `_wait_until(9, 0)` helper *before* `wait_for_market_open()`,
   so the open/close-game tasks fire 15 minutes earlier than before, then the poller keeps waiting for
   the market to actually open before polling starts. `_wait_until()` is itself a no-op if the process
   happens to start after 09:00 (e.g. a late restart), so this degrades safely.

Both constants kept separate from `MARKET_OPEN_IST`/`MARKET_CLOSE_IST` — they're genuinely different
moments (the market-hours boundary vs. when *this game's* answer becomes effectively fixed), not
duplicated values that happen to coincide.

## Why chained, not clock-scheduled

First design used fixed clock times (create next day's game at 18:00, create today's close-game at
10:00 AM) via the poller's already-unused `_wait_until()` helper. User redirected: chain the creation
of each game directly off the resolution of the other instead — resolving the close-game immediately
opens tomorrow's open-game, resolving the open-game immediately opens today's close-game. This is
simpler (no new clock-time hooks, no risk of the 18:00/10:00 wait drifting out of sync with the actual
resolve step) and removes the two dedicated timing hooks entirely — game creation is a direct
consequence of the other game finishing, not a coincidentally-nearby scheduled event.

## Reward mechanic — new generic capability, not auto-game-specific

User's economics: **one winner only, and only if within 10 points of the actual value; if nobody is
that close, nobody is paid.** This doesn't fit the existing `resolve_game()` behavior (always pays the
closest N entries regardless of how close they actually are), so `resolve_game()` gained one new
optional parameter: `win_threshold: float | None = None`. When set, an entry's rank alone no longer
qualifies it for `credits_won` — it also needs `score <= win_threshold`. `None` (every existing caller,
i.e. every admin manual resolve) preserves the exact old behavior — zero regression risk for manual
games. Only this feature's own two call sites ever pass a threshold.

Values used (`backend/config.py`, explicit — not defaulted then special-cased):

```python
GAME_NIFTY_OPEN_REWARD_POOL    = 50   # credits
GAME_NIFTY_OPEN_WIN_THRESHOLD  = 10   # points
GAME_NIFTY_CLOSE_REWARD_POOL   = 50
GAME_NIFTY_CLOSE_WIN_THRESHOLD = 10
```

Both games: `winner_count=1`.

## New `games.auto_kind` column

Nullable TEXT, `NULL` for every admin-created game. `'nifty_next_open'` / `'nifty_today_close'` for
these two. Lets the automation find "the currently pending game I own" without ever touching an
admin-created `price_prediction` game of the same `game_type`. Two lookup helpers, since a game now
spends real time in each state: `get_active_auto_game(kind)` (`draft`/`active` — still open for
entries, used when closing entries) and `get_closed_auto_game(kind)` (`closed` — entries locked,
awaiting the EOD resolve). See `docs/schema.md`.

## Attribution: no system/bot user exists

`games.created_by` is `NOT NULL REFERENCES users(id)`. There's no dedicated bot/system account in this
schema, so automated games are attributed to the oldest `super_admin` user
(`db/queries.get_system_user_id()` — `upsert_user()` already makes the first-ever signup `super_admin`
unconditionally, so one always exists).

## Where the automation lives — reusing the poller's existing 24/7 process, not a new cron job

`edgevest-poller.service` is `Restart=always`: each day's `run_live()` call runs market hours, does EOD
tasks (~16:05), and exits; systemd restarts it ~30s later, and the new invocation immediately re-enters
`wait_for_market_open()`, sleeping until the next 09:15. So the process only *looks* like it exits and
restarts daily — in practice, since nothing else crashes it, it's continuously alive across the
16:05→09:15 idle window. Three new hook points, no new process/cron/systemd unit:

1. **At `GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST` (09:00), via `_wait_until(9, 0)` before
   `wait_for_market_open()`** (`_run_market_open_game_tasks()`, `--force`-gated off) — closes entries on
   the open-game (does not resolve it), then creates today's close-game. `_wait_until()` had sat unused
   in this file since it was originally built for an earlier (later-abandoned) clock-scheduled design —
   this is its first real use.
2. **Inside the main poll loop, once per day, the moment the clock crosses
   `GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST`** (`_run_close_entry_cutoff_task()`, guarded by a
   `_close_entries_done` flag) — closes entries on the close-game (does not resolve it).
3. **Inside `_run_eod_tasks()`, right after `run_daily_sync()`** (`_run_eod_game_tasks()`) — fetches
   `get_candles("NIFTY50", "1d", limit=1)` once, resolves the open-game from its `open` column and the
   close-game from its `close` column, then creates the next open-game via `holidays.next_trading_day()`.

Every step is wrapped in its own `try/except` — a failure on one game/action doesn't block the others,
matching every other best-effort task in `_run_eod_tasks()`/the poll loop. Every creation step is
duplicate-guarded via `get_active_auto_game()` — a poller crash-and-restart mid-window re-runs the same
hook, but never creates a second game for the same slot.

## Related bug fixed in the same pass: `wait_for_market_open()` never checked the day

Found while reading this code path: `is_market_open()` only ever checked time-of-day (`MARKET_OPEN_IST`
≤ now ≤ `MARKET_CLOSE_IST`), never day-of-week. The only reason the poller has never actually polled on
a Saturday is that `check_or_exit()` (which does check the day) runs exactly once, at process start —
and every trading-day process just happens to still be alive, idling in `wait_for_market_open()`, when
Saturday/Sunday roll past. That was one `is_trading_day()` call away from silently failing the first
time a restart happened to land differently. Fixed: `wait_for_market_open()`'s loop condition is now
`while not (is_trading_day() and is_market_open())` — `is_trading_day()` re-evaluates `date.today()`
every 60s iteration, so this now correctly rides out an entire weekend/holiday block, however many
days long, instead of being safe only by accident.

## A real prod bug found while dogfooding: EOD resolution used yesterday's candle

2026-09-23, from a fresh prod DB pull: both games had already resolved, but with visibly wrong
open/close values. Root-caused with real data, not guessed:

- **The actual cause, not games-specific:** `bootstrap/upstox_loader.py`'s `_is_incomplete_last_candle()`
  — the function deciding whether to drop the freshest fetched candle as "still forming" — had, for the
  `1d` timeframe, `return last_ist.date() == now_ist.date()`. This drops a candle whenever it's dated
  *today*, with **no check on the actual time** — so even the 16:00 EOD sync (deliberately scheduled
  30min after the 15:30 close specifically because Upstox's data is final by then) always threw today's
  own candle away, every single day, forever. `candles_1d` was permanently one full day stale right
  after every EOD sync, only ever caught up by the *next* day's sync. This silently affected every 1d
  consumer in the system (monthly reports, strategies), not just these games — just never surfaced
  loudly before because nothing else needed *same-day* 1d data. **Fixed:** the 1d check now also
  requires we're actually before market close on that same date — a same-day candle is only "still
  forming" until `MARKET_CLOSE_IST`, not for the entire rest of the day. Verified directly: today's
  candle at the real current time (past close) → correctly kept; same candle simulated at 10:00 IST
  (before close) → still correctly dropped; a different day's candle → unaffected either way.
- **Games-specific defensive fix, on top:** `_run_eod_game_tasks()` previously trusted
  `get_candles("NIFTY50", "1d", limit=1)`'s "most recent row" with no date check at all. Now compares
  the fetched candle's date (converted to IST) against today's actual date — if they don't match, both
  games are left `closed` (not resolved) rather than silently graded against stale data, logged clearly
  ("still shows yesterday's session"). This is the safety net for *any* reason today's candle might be
  missing (not just the bug above — a genuine Upstox delay, a failed sync, anything) — recoverable via
  `poller.py games eod` once real data exists, same recovery path as "no candle at all yet". Verified
  in isolation: stale-candle-only scenario → both games correctly stay unresolved; re-run once a
  same-day candle is added → both resolve correctly.
- **Not retroactively fixed:** the two prod games that had already resolved with wrong values before
  this fix were left as-is — `get_closed_auto_game()` won't find an already-`resolved` game, so a
  re-run can't silently correct them, and doing so would touch already-paid-out credits, a decision
  left to the user rather than made unilaterally. (Turned out moot: checked, and every entry in both
  games had `credits_won=0` — the closest guess was still outside the 10-point `win_threshold` even
  against the wrong values, so nothing was actually paid out incorrectly. No clawback needed.)

## A real prod incident: a late poller restart created an exploitable duplicate game

2026-09-23, 22:37 IST — deploying `v7.7.13`/`v7.7.14` meant manually restarting
`edgevest-poller.service`, and that restart happened after 09:00 IST. `_wait_until(9, 0)` only
*waits* if called before 09:00 — called later, it's a no-op, so `_run_market_open_game_tasks()` fired
immediately at 22:37 instead of waiting for a real 09:00. Confirmed via the real prod log:

```
22:37:06  [games]  closed entries on 'Predict NIFTY's Open — Thu, 24 Sep 2026' — resolves at EOD
22:37:06  [games]  created & activated "Predict NIFTY's Close — Wed, 23 Sep 2026" (id=8)
```

Two real problems, not just a benign duplicate:
1. **Tomorrow's already-created open-game got closed 10+ hours early** — it was legitimately created
   at today's 16:00 EOD for Thursday, meant to stay open until Thursday 09:00. Inconvenient (cuts entry
   time short), not dangerous — resolves correctly at Thursday's EOD regardless.
2. **A duplicate close-game got created for a trading day that had already fully closed out** —
   Wednesday's real close was already public (resolved in the original close-game, hours earlier).
   `get_active_auto_game("nifty_today_close")`'s existing duplicate-guard didn't catch this, because the
   *original* Wednesday close-game was already `resolved` (not `active`) by 22:37 — so from that guard's
   point of view, no active close-game existed, clearing the way for a new one. **This was actively
   exploitable**: anyone could enter the duplicate with the already-known correct answer for a
   guaranteed win. Worse, `auto_kind` games have their manual admin Close button hidden (`v7.7.12`), so
   it couldn't even be closed from the UI — required direct DB access to shut down.

**Fixed:** `_run_market_open_game_tasks()` now checks, before doing anything, whether the currently
active `nifty_next_open` game's own `end_time` falls on *today* — new `_game_end_date_ist()` helper. If
EOD already ran today (the normal state on a late restart), the active open-game is legitimately
tomorrow's, and the function now skips entirely rather than touching it. Verified by reproducing the
exact prod scenario in isolation (today's close-game resolved, tomorrow's open-game active, fire the
function) — tomorrow's game stays untouched, no duplicate created; and by a regression check confirming
the normal same-day case still works exactly as before.

**Lesson for any future clock-anchored hook using `_wait_until()`'s no-op-if-already-past behavior:**
that pattern is only safe if the action itself is idempotent *and* self-aware of which day it's actually
supposed to affect — a duplicate-guard alone isn't enough if the state that guard checks can have already
moved on (e.g. from `active` to `resolved`) by the time a late trigger fires.

## Follow-on incident, 2026-09-24: the fix above was necessary but not sufficient

The `_game_end_date_ist()` guard correctly made `_run_market_open_game_tasks()` *skip* touching a
not-yet-due game on a late restart — but that guard only decides what to do the moment it's called, and
it's only ever called once per process lifetime (right before `wait_for_market_open()`). 2026-09-24: the
previous night's restart (22:37 IST) hit exactly this path, correctly skipped touching the 24th's
open-game (not due yet, relative to the 23rd), then the process fell into `wait_for_market_open()`'s idle
loop and sat there overnight. Nothing re-checked the 09:00 cutoff once the *24th's own* 09:00 genuinely
arrived — that check was a single call, already spent on the correct skip the night before — so the
open-game stayed stuck `active` for ~20 minutes until manually triggered (`poller.py games open`).

**Fixed properly this time:** moved the cutoff recheck *inside* `wait_for_market_open()`'s own loop
(tracking a `serviced_date` so it fires at most once per calendar date), rather than leaving it as a
one-shot call before the loop. Exactly the same shape as that loop's pre-existing `is_trading_day()`
recheck just above (§"Related bug... never checked the day") — this was the identical class of bug,
just not caught until it actually happened a second time. Verified with a simulated stuck-across-midnight
scenario (monkeypatched clock, confirms the new day gets its own fire attempt) plus the unchanged normal
single-day case.

**General principle for any future poller schedule/cutoff logic**, not just this feature: memory
`feedback_poller_recurring_schedule_design` — the short version is *check every iteration of whichever
idle loop the process might be sitting in when the target time arrives, never a call at a fixed point
before/after that loop.*

## The real fix: Upstox has a separate API for today's data — we were never calling it

The `_is_incomplete_last_candle()` fix above helps, but doesn't fully solve same-day resolution —
confirmed by testing live against Upstox for hours after close: the **Historical Candle API**
(`get_historical_candles()`, what `fetch_historical()`/`bootstrap/upstox_loader.py` has always used) is
**documented to only ever serve completed historical days**. It structurally never returns the current
trading day, no matter what time you ask — that's by design, not a publish delay to wait out.

Upstox has a **separate, dedicated endpoint** for exactly this: the **Intraday Candle Data V3 API**
(`get_intra_day_candle_data` — already present in the installed SDK, just never called from this
codebase). Verified live, hours after close: `days`/`1` on this endpoint returned today's full,
accurate OHLC (`open=23352.15, close=23446.8`) — matching independently-confirmed-correct values
exactly. Also verified across `1m`/`5m`/`15m`/`1h` — all agree, all correct. (This also explains an
earlier red herring in this same debugging thread: our own poller's first captured tick landed at
09:15:09, 9 seconds after market open, and NIFTY had already moved from 23352.15 to ~23404 by then —
Upstox's own exchange-timed 1-minute candle caught the true 09:15:00 print; our own tick-polling loop
structurally can't guarantee that, since there's always some non-zero delay before the first request
lands.)

**Fixed at the sync-pipeline level, not just for games** (`sync/daily_sync.py`'s `sync_symbol()`): now
calls both APIs with a clean split of responsibility — `fetch_historical()` keeps backfilling/correcting
everything *older* than today (unchanged), and a new `fetch_intraday()` (`bootstrap/upstox_loader.py`,
wrapping the new `get_intraday_candles()` in `live/upstox_client.py`) fills in *today* specifically, via
the intraday endpoint, for `1m`/`5m`/`15m`/`1h`/`1d` (the intraday endpoint has no `weeks`/`months`
unit, so `1wk`/`1mo` stay historical-only — "this week"/"this month" being incomplete until it ends
isn't a same-day gap anything currently needs). Both write through the same `upsert_candles()`, so every
downstream reader — games, monthly reports, strategies — just reads `candles_1d` etc. normally and gets
complete, correct same-day data, with no awareness that either of this exists.

**Verified end-to-end** against a temp copy of the real (still-missing-today) prod DB: `candles_1d` went
from 4668 → 4669 rows for NIFTY50, the new row exactly matching the confirmed-correct
`open=23352.15, close=23446.8`; `1h` also picked up its final partial-hour boundary that the local
tick-builder hadn't closed yet. The games feature needs **no special-casing at all** now — it already
reads `candles_1d` normally; this just makes that table actually correct same-day. The earlier
date-staleness check in `_run_eod_game_tasks()` stays in place as a defensive backstop (e.g. if the
intraday fetch itself fails on some day), not as the primary mechanism anymore.

## Two UI bugs found while dogfooding this feature (`v7.7.11`, `v7.7.12`)

Not part of the automation itself, but found and fixed in the same arc, testing this
exact feature end-to-end:

- **Wrong local time instead of IST.** `Games.jsx`/`GameDetail.jsx` each had their own
  local `fmtIst()` reimplementation with backwards `Z`-handling — it stripped a
  trailing `Z` and never re-added it, so `new Date(...)` parsed the timestamp using
  the *machine's own local timezone* instead of UTC. On a non-UTC machine this showed
  e.g. "10:00 am" for a game whose `end_time` actually meant 3:30 pm IST. The rest of
  the app was never affected — everywhere else already used the correctly-written
  shared `fmtIstShort()` in `utils/format.js`; only these two Games files had their
  own broken copy. Fixed by deleting both duplicates and switching every call site
  to the shared helper.
- **Hardcoded "close" wording.** `PredictionGame`'s copy ("Predicted close for
  NIFTY50", "Actual close", "Where will it close on...") assumed `price_prediction`
  always meant predicting a close — wrong for the new open-prediction game, which
  literally said "close" everywhere. Now derived from the game's title
  (`/open/i.test(game.title)`), the same convention the automation uses to name its
  own games. Also hid `AdminActions`' manual "Close Game"/"Resolve & Award Credits"
  buttons for any `auto_kind` game — either would have fought the automation (closing
  entries early, or resolving without the `win_threshold` payout rule this screen's
  resolve action never applies, silently paying the top-ranked entry regardless of
  how far off they actually were).

## Verification (isolated temp SQLite DB, no side effects on the real dev DB)

- `next_trading_day(Fri 2026-09-25)` → `Mon 2026-09-28` (correctly skips the weekend).
- `resolve_game(..., win_threshold=10)`: entry 5 points off → paid the full 50-credit pool; entry 205
  points off (same game) → `credits_won=0`. Separate game where the closest entry is 995 points off
  (still "first place" by rank) → `credits_won=0` for both entries — confirms "nobody pays" when no one
  actually qualifies, not just "the top-ranked entry always gets something."
- Full simulated day cycle with the 3-step chain: `_run_eod_game_tasks()` (day 0, nothing to resolve
  yet) → creates open-game → `_run_market_open_game_tasks()` → closes open-game entries (confirmed
  `status='closed'`, `result_value=None` — not yet graded), creates close-game → entries submitted to
  both games → `_run_close_entry_cutoff_task()` → closes close-game entries (same closed-not-resolved
  check) → inserted one fake `candles_1d` row (`open=25010, close=25060`) → `_run_eod_game_tasks()` →
  both games resolved in the same call from that one row (`open-game: result_value='25010.0'`,
  `close-game: result_value='25060.0'`), correct winner picked in each (the entry within 10 points),
  next open-game created. Titles carried the correct target date at every step. Re-run after the
  09:00/15:00 safety-margin correction: open-game `end_time` landed on `03:30:00Z` (09:00 IST) and
  close-game `end_time` on `09:30:00Z` (15:00 IST) — both exact.
- Duplicate-call guard: calling `_run_eod_game_tasks()` again immediately after (simulating a same-
  window poller restart) logged "already exists — skipping create" and left the total `nifty_next_open`
  row count unchanged.

## Deploy

No frontend changes at all — `price_prediction` games already fully render/enter/resolve through the
existing Games UI, and admin-created games are entirely unaffected (`win_threshold` defaults to `None`
everywhere else). Needs:

- `python poller.py init` — creates the new `games.auto_kind` column.
- Restart the poller (`edgevest-poller.service`) — picks up the new hook points and the
  `wait_for_market_open()` fix.
- No backend-web restart required (`server.py` itself is unchanged) — but bump `APP_VERSION` and deploy
  per the usual release convention anyway, since `db/queries.py`/`config.py` changed.

## Manual trigger (testing, or recovering a missed run)

`python poller.py games open|cutoff|eod` — thin CLI wrappers (`backend/poller.py`) around the exact
same three functions the live poller calls automatically, so this is a real trigger against real data,
not a simulation: `eod` reads the actual `candles_1d` open/close. All three are idempotent (the
existing `get_active_auto_game()`/`get_closed_auto_game()` guards apply identically) — safe to re-run,
e.g. after confirming a scheduled step didn't fire. Lets the full lifecycle be tested end-to-end
without waiting for real 09:00/15:00/16:00 IST.
