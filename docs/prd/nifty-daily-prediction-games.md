# Daily NIFTY open/close prediction games — fully automated

**Status:** built 2026-09-22. Reuses the existing `price_prediction` game type end-to-end (schema,
`/api/games*` routes, frontend create/enter/resolve UI — none of it changed); the only new thing is
automation inside `live/poller.py` that runs the two games' full lifecycle without any admin click.

## What it does

Two `price_prediction` games run every trading day. Entries close promptly for each, but **neither is
resolved until the 16:00 EOD sync** — see "Why both resolve at EOD" below.

1. **"Predict NIFTY's Open — `<date>`"** — created at EOD the evening before, for whichever day is the
   next actual trading day (`holidays.next_trading_day()` — skips weekends/holidays, so a Friday's EOD
   can jump straight to the following Monday, or further over a long weekend). Entries close the
   instant the market opens (09:15) — once NIFTY starts trading the answer is no longer a fair guess —
   but it isn't graded until EOD.
2. **"Predict NIFTY's Close — `<date>`"** — created the moment the open-game's entries close (09:15,
   same instant, same function call), for *today*. Entries close at 15:00 (`GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST`,
   30 minutes before the real 15:30 close, same "lock entries before the answer is nearly certain"
   logic as the open-game), also not graded until EOD.

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
— entries still lock promptly (09:15 for open, 15:00 for close), only the grading/payout is deferred
to when real data exists. Both games are graded from **one shared `candles_1d` row fetch** at EOD, so
they're always consistent with each other and with the same sync that produces every other candle in
this system.

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

1. **Right after `wait_for_market_open()` returns** (`_run_market_open_game_tasks()`, called once
   before the main poll loop starts, `--force`-gated off) — closes entries on the open-game (does not
   resolve it), then creates today's close-game.
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
  next open-game created. Titles carried the correct target date at every step.
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
without waiting for real 09:15/15:00/16:00 IST.
