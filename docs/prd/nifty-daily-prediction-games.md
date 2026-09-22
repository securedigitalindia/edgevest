# Daily NIFTY open/close prediction games — fully automated

**Status:** built 2026-09-22. Reuses the existing `price_prediction` game type end-to-end (schema,
`/api/games*` routes, frontend create/enter/resolve UI — none of it changed); the only new thing is
automation inside `live/poller.py` that runs the two games' full lifecycle without any admin click.

## What it does

Two `price_prediction` games run every trading day, back to back, chained off each other rather than
fixed clock times:

1. **"Predict NIFTY's Open — `<date>`"** — created the moment the *previous* game (below) is resolved
   at EOD, for whichever day is the next actual trading day (`holidays.next_trading_day()` — skips
   weekends/holidays, so a Friday's EOD can jump straight to the following Monday, or further over a
   long weekend). Entries close automatically the instant the market opens — closing entries at market
   open, not letting them run right up to the answer, is the point: once NIFTY starts trading the
   answer is no longer a fair guess. Resolved on the poller's first tick of the day, using that tick's
   NIFTY50 LTP as the actual open.
2. **"Predict NIFTY's Close — `<date>`"** — created the moment game 1 is resolved (same instant, same
   function call), for *today*. Resolved after the 16:00 EOD Upstox sync, using the official
   `candles_1d` close (not a raw 15:30 LTP snapshot — the EOD sync just made that value final, so
   there's no reason to guess with an approximate one).

Every title/description always states the target date explicitly (user requirement — these run daily,
so "Predict NIFTY's Close" alone would be ambiguous about which day on the games list).

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
these two. Lets the automation find "the currently pending game I own" (`get_active_auto_game(kind)`
— most recent `draft`/`active` row with that `auto_kind`) without ever touching an admin-created
`price_prediction` game of the same `game_type`. See `docs/schema.md`.

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
16:05→09:15 idle window. Four new hook points, no new process/cron/systemd unit:

1. **First tick after market open** (`_run_market_open_game_tasks()`, called once from the main poll
   loop, guarded by a `_market_open_game_tasks_done` flag that only latches once a NIFTY50 LTP is
   actually present in that tick's prices) — resolves the open-game, then creates the close-game.
2. **Inside `_run_eod_tasks()`, right after `run_daily_sync()`** (`_run_eod_game_tasks()`) — resolves
   the close-game using `get_candles("NIFTY50", "1d", limit=1)`, then creates the next open-game via
   `holidays.next_trading_day()`.

Both are `--force`-gated off (skipped entirely under `poller.py live --force`, the same flag every
other EOD/day-boundary task already respects) so a manual test run never creates real games. Both
halves of each function are independently wrapped in `try/except` — a failure resolving one game
doesn't block creating the other, matching every other best-effort task in `_run_eod_tasks()`/the poll
loop. Both creation steps are duplicate-guarded via `get_active_auto_game()` — a poller crash-and-
restart mid-window re-runs the same hook, but never creates a second game for the same slot.

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
- Full simulated day cycle: `_run_eod_game_tasks()` (day 1, nothing to resolve yet) → creates open-game
  → `_run_market_open_game_tasks(25010.0)` → resolves open-game, creates close-game → (inserted a fake
  `candles_1d` close row) → `_run_eod_game_tasks()` → resolves close-game, creates next open-game.
  Titles carried the correct target date at every step.
- Duplicate-call guard: calling `_run_eod_game_tasks()` again immediately after (simulating a same-
  window poller restart) logged "already exists — skipping create" and left the total `nifty_next_open`
  row count unchanged (2, not 3).

## Deploy

No frontend changes at all — `price_prediction` games already fully render/enter/resolve through the
existing Games UI, and admin-created games are entirely unaffected (`win_threshold` defaults to `None`
everywhere else). Needs:

- `python poller.py init` — creates the new `games.auto_kind` column.
- Restart the poller (`edgevest-poller.service`) — picks up the new hook points and the
  `wait_for_market_open()` fix.
- No backend-web restart required (`server.py` itself is unchanged) — but bump `APP_VERSION` and deploy
  per the usual release convention anyway, since `db/queries.py`/`config.py` changed.
