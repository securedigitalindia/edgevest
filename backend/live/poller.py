"""
Drishti — Live Poller
=====================
Run:
    python poller.py live
    python poller.py live --force    # skip market-hours + holiday check (for testing)

Daily lifecycle:
  Startup   : holiday check → expiry cache refresh → build triggers
  09:00 IST : (15min safety margin before market open) — close entries on
              yesterday evening's NIFTY open-prediction game (not resolved
              yet), open today's NIFTY close-prediction game
  09:15 IST : market opens
  Market hrs: poll every 5s → store ticks → run triggers → build 1h candles at :15 boundary
  15:00 IST : (15min safety margin before NIFTY's real/effective 15:15
              close, not the 15:30 market-hours boundary) — close entries
              on today's NIFTY close-prediction game (not resolved yet)
  16:00 IST : daily Upstox sync → resolve BOTH of today's NIFTY games from
              the now-available official candles_1d open/close → open
              tomorrow's NIFTY open-prediction game → tick cleanup →
              expiry cache refresh → exit
  (see docs/prd/nifty-daily-prediction-games.md for the games themselves —
  neither game is resolved until 16:00, since candles_1d's open/close don't
  exist before that sync runs)
"""

import argparse
import sys
import os
import time
import gc
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    SYMBOLS,
    TRIGGERS,
    UPSTOX_INSTRUMENT_KEYS,
    POLL_INTERVAL_SECONDS,
    MARKET_OPEN_IST,
    MARKET_CLOSE_IST,
    GAME_NIFTY_OPEN_REWARD_POOL,
    GAME_NIFTY_OPEN_WIN_THRESHOLD,
    GAME_NIFTY_CLOSE_REWARD_POOL,
    GAME_NIFTY_CLOSE_WIN_THRESHOLD,
    GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST,
    GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST,
)
from live.upstox_client import get_ltp
from live.triggers import build_trigger, BaseTrigger
from live.alert import send_alert
from live.expiry import expiry_cache
from live.intraday_sync import CandleWatcher
from live import tick_store, candle_builder, option_chain_capture, chain_triggers
from live.holidays import check_or_exit, is_trading_day, next_trading_day
from live.fo_instruments import SPOT_IKEYS
from db.queries import (
    update_price_cache, get_open_trade_ikeys, get_candles,
    get_active_auto_game, get_closed_auto_game, create_game, set_game_status,
    resolve_game, get_system_user_id,
)

IST = ZoneInfo("Asia/Kolkata")

# ---------------------------------------------------------------------------
# Market hours
# ---------------------------------------------------------------------------

def _ist_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(IST)


def _ist_minutes() -> int:
    t = _ist_now()
    return t.hour * 60 + t.minute


def is_market_open() -> bool:
    m = _ist_minutes()
    return (MARKET_OPEN_IST[0] * 60 + MARKET_OPEN_IST[1]
            <= m <=
            MARKET_CLOSE_IST[0] * 60 + MARKET_CLOSE_IST[1])


def wait_for_market_open():
    """
    Blocks until it's actually time to poll. is_market_open() alone only
    checks time-of-day — it has no idea what day it is, so on its own this
    loop would happily consider 09:15 on a Saturday "open". The process only
    re-runs check_or_exit() (which does know the day) once, at startup —
    if that happens on a Friday evening, this loop would otherwise sit here
    and start polling Saturday morning. is_trading_day() re-evaluates
    date.today() every iteration, so this correctly rides out an entire
    weekend/holiday block, however many days long.
    """
    print("Market not yet open. Waiting for 09:15 IST on a trading day...\n", flush=True)
    while not (is_trading_day() and is_market_open()):
        print(f"  {_ist_now().strftime('%a %H:%M:%S IST')}  — waiting...", flush=True)
        time.sleep(60)
    print("Market open. Starting poll loop.\n", flush=True)


def _wait_until(target_hour: int, target_minute: int = 0):
    """Sleep until target HH:MM IST today. No-op if already past."""
    now = _ist_now()
    target = now.replace(hour=target_hour, minute=target_minute,
                         second=0, microsecond=0)
    secs = (target - now).total_seconds()
    if secs > 0:
        print(f"  Waiting {secs/60:.0f} min until "
              f"{target_hour:02d}:{target_minute:02d} IST...", flush=True)
        time.sleep(secs)


# ---------------------------------------------------------------------------
# Startup and EOD task bundles
# ---------------------------------------------------------------------------

def _run_startup_tasks():
    """
    Run at poller startup before market opens.
    Only refreshes expiry cache — no Upstox candle sync here because the market
    may already be open and the provider would return an incomplete in-progress
    candle for today. The EOD sync at 16:00 IST is the right time to sync
    (market closed by then).
    """
    print("── Startup tasks ──────────────────────────────────")
    print("Refreshing option expiry dates from Upstox...\n")
    try:
        expiry_cache.refresh()
    except Exception as e:
        print(f"  [expiry refresh failed]  {e}", flush=True)

    try:
        from live.fo_instruments import refresh as refresh_fo
        refresh_fo()
    except Exception as e:
        print(f"  [F&O instruments refresh failed]  {e}", flush=True)

    print("───────────────────────────────────────────────────\n")


def _run_chain_triggers_safe():
    """Thread target for chain_triggers.run_chain_triggers() — an uncaught exception in a
    background thread doesn't crash the poller, but prints Python's default (noisy) traceback;
    this keeps the log line consistent with every other best-effort task here."""
    try:
        chain_triggers.run_chain_triggers()
    except Exception as e:
        print(f"  [chain triggers failed]  {e}", flush=True)


def _utc_iso(dt) -> str:
    """IST-aware datetime → UTC ISO string, matching db/queries.py's _now_utc() format."""
    from datetime import timezone as _tz
    return dt.astimezone(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _game_end_date_ist(game: dict):
    """The IST calendar date a game's end_time falls on — used to check
    whether a game found via get_active_auto_game() is actually the one
    meant to transition *today*, not some other day's."""
    dt = datetime.strptime(game["end_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()


def _run_market_open_game_tasks():
    """
    Normally called once, at GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST (09:00 — 15min
    BEFORE market open, a deliberate safety margin against last-second
    entries, not the market-open moment itself; see the _wait_until() call
    in run_live(), before wait_for_market_open()).

    BUT: _wait_until() only *waits* if called before 09:00 — if the poller
    process happens to (re)start later than that (e.g. a manual restart for
    a deploy, at any hour), this still runs immediately, whatever the actual
    clock time is. Confirmed in prod 2026-09-23: a 22:37 IST restart fired
    this, which — before this guard existed — closed *tomorrow's*
    already-created open-game 10+ hours early and created a *duplicate*
    "today's close" game for a trading day that had already fully closed out
    hours earlier (exploitable: that day's real close was already public in
    the original, already-resolved close-game, so anyone could've entered
    the duplicate with a guaranteed-correct guess). Guard: only actually act
    if the found open-game's own end_time falls on *today* — if EOD already
    ran today (the normal case on a late restart), the active open-game is
    legitimately tomorrow's, not today's, and must not be touched here.

    Two independent steps chained by timing, not by outcome — either can
    fail on its own without blocking the other:
      1. Close entries on last evening's "predict NIFTY's open" game — done
         with a margin before the answer becomes knowable at market open,
         not right at it. NOT resolved yet: candles_1d's official open
         doesn't exist until the 16:00 EOD sync (see _run_eod_game_tasks()),
         so this is graded then, alongside today's close-game, from the same
         authoritative source rather than an approximate live-LTP snapshot.
      2. Create + activate today's "predict NIFTY's close" game.
    See docs/prd/nifty-daily-prediction-games.md.
    """
    game = get_active_auto_game("nifty_next_open")
    if not game:
        print("  [games]  no pending open-prediction game to close "
              "(none created last evening?)", flush=True)
        return
    if _game_end_date_ist(game) != _ist_now().date():
        print(f"  [games]  active open-game '{game['title']}' targets a different day than "
              f"today — already past today's transition (likely a late restart), skipping",
              flush=True)
        return

    try:
        set_game_status(game["id"], "closed")
        print(f"  [games]  closed entries on '{game['title']}' — resolves at EOD", flush=True)
    except Exception as e:
        print(f"  [games]  failed to close open-prediction game — {e}", flush=True)

    try:
        if get_active_auto_game("nifty_today_close"):
            print("  [games]  today's close-prediction game already exists — skipping create", flush=True)
            return
        today = _ist_now()
        label = today.strftime("%a, %d %b %Y")
        cutoff_h, cutoff_m = GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST
        cutoff = today.replace(hour=cutoff_h, minute=cutoff_m, second=0, microsecond=0)
        gid = create_game(
            title=f"Predict NIFTY's Close — {label}",
            description=f"Guess where NIFTY 50 closes today ({label}). Entries close at "
                        f"{cutoff_h:02d}:{cutoff_m:02d} IST, NIFTY's real/effective close. "
                        f"Closest guess within {GAME_NIFTY_CLOSE_WIN_THRESHOLD} points of the actual "
                        f"close wins {GAME_NIFTY_CLOSE_REWARD_POOL} credits — no winner if nobody's "
                        f"close enough. Results announced after market close, once official data "
                        f"confirms it.",
            game_type="price_prediction", symbol="NIFTY50",
            start_time=_utc_iso(today), end_time=_utc_iso(cutoff),
            reward_pool=GAME_NIFTY_CLOSE_REWARD_POOL, winner_count=1,
            initial_cash=1_000_000, created_by=get_system_user_id(),
            auto_kind="nifty_today_close",
        )
        set_game_status(gid, "active")
        print(f"  [games]  created & activated \"Predict NIFTY's Close — {label}\" (id={gid})", flush=True)
    except Exception as e:
        print(f"  [games]  failed to create today's close-prediction game — {e}", flush=True)


def _run_close_entry_cutoff_task():
    """
    Called once, when the clock crosses GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST
    (15:00 — a 15min safety margin before NIFTY's real/effective 15:15
    close, not MARKET_CLOSE_IST's 15:30; see the `_close_entries_done`
    guard in the poll loop below). Only closes
    entries on today's "predict NIFTY's close" game — not resolved until
    EOD, alongside the open-game (see _run_eod_game_tasks()).
    """
    try:
        game = get_active_auto_game("nifty_today_close")
        if game:
            set_game_status(game["id"], "closed")
            print(f"  [games]  closed entries on '{game['title']}' — resolves at EOD", flush=True)
        else:
            print("  [games]  no pending close-prediction game to close "
                  "(none created this morning?)", flush=True)
    except Exception as e:
        print(f"  [games]  failed to close close-prediction game — {e}", flush=True)


def _run_eod_game_tasks():
    """
    Called from _run_eod_tasks(), after the Upstox EOD sync — candles_1d has
    today's official open AND close by then (neither exists in this system
    before that sync runs). Resolves both of today's games from that one
    candle, then creates the next trading day's open-game:
      1. Resolve today's "predict NIFTY's open" game (entries closed at
         GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST, 09:00) using the candle's `open`.
      2. Resolve today's "predict NIFTY's close" game (entries closed at
         GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST, 15:00) using the candle's `close`.
      3. Create + activate a "predict NIFTY's open" game for the next
         trading day (may be several days out over a weekend/holiday block).
    See docs/prd/nifty-daily-prediction-games.md.
    """
    candles = get_candles("NIFTY50", "1d", limit=1)
    today_ist = _ist_now().date()
    # get_candles(limit=1) returns whatever the MOST RECENT row is — with no
    # date check, a delayed/failed Upstox sync (confirmed to happen: sync_log
    # can show a "successful" run that still didn't yet have today's candle)
    # would silently resolve today's games against YESTERDAY's open/close.
    # Both games then just stay 'closed' (never 'resolved') until a manual
    # `poller.py games eod` re-run once the real candle exists — same
    # recovery path as "no candle available at all".
    stale = not candles.empty and candles.iloc[-1]["ts"].tz_convert("Asia/Kolkata").date() != today_ist
    if candles.empty or stale:
        reason = "still shows yesterday's session" if stale else "no NIFTY50 daily candle available yet"
        print(f"  [games]  {reason} — leaving today's games unresolved this cycle", flush=True)
    else:
        today_candle = candles.iloc[-1]

        try:
            game = get_closed_auto_game("nifty_next_open")
            if game:
                actual_open = float(today_candle["open"])
                resolve_game(game["id"], result_value=str(actual_open),
                             win_threshold=GAME_NIFTY_OPEN_WIN_THRESHOLD)
                print(f"  [games]  resolved '{game['title']}' — open={actual_open}", flush=True)
            else:
                print("  [games]  no closed open-prediction game to resolve "
                      "(missed the market-open close-entries step?)", flush=True)
        except Exception as e:
            print(f"  [games]  failed to resolve open-prediction game — {e}", flush=True)

        try:
            game = get_closed_auto_game("nifty_today_close")
            if game:
                actual_close = float(today_candle["close"])
                resolve_game(game["id"], result_value=str(actual_close),
                             win_threshold=GAME_NIFTY_CLOSE_WIN_THRESHOLD)
                print(f"  [games]  resolved '{game['title']}' — close={actual_close}", flush=True)
            else:
                print("  [games]  no closed close-prediction game to resolve "
                      "(missed the close-entries-cutoff step?)", flush=True)
        except Exception as e:
            print(f"  [games]  failed to resolve close-prediction game — {e}", flush=True)

    try:
        if get_active_auto_game("nifty_next_open"):
            print("  [games]  next open-prediction game already exists — skipping create", flush=True)
            return
        now = _ist_now()
        target = next_trading_day(now.date())
        label = target.strftime("%a, %d %b %Y")
        open_cutoff_h, open_cutoff_m = GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST
        open_at = now.replace(year=target.year, month=target.month, day=target.day,
                              hour=open_cutoff_h, minute=open_cutoff_m,
                              second=0, microsecond=0)
        gid = create_game(
            title=f"Predict NIFTY's Open — {label}",
            description=f"Guess where NIFTY 50 opens on {label}. Entries close at "
                        f"{open_cutoff_h:02d}:{open_cutoff_m:02d} IST, shortly before market open. "
                        f"Closest guess within {GAME_NIFTY_OPEN_WIN_THRESHOLD} points "
                        f"of the actual open wins {GAME_NIFTY_OPEN_REWARD_POOL} credits — no winner "
                        f"if nobody's close enough. Results announced after market close, once "
                        f"official data confirms the actual open.",
            game_type="price_prediction", symbol="NIFTY50",
            start_time=_utc_iso(now), end_time=_utc_iso(open_at),
            reward_pool=GAME_NIFTY_OPEN_REWARD_POOL, winner_count=1,
            initial_cash=1_000_000, created_by=get_system_user_id(),
            auto_kind="nifty_next_open",
        )
        set_game_status(gid, "active")
        print(f"  [games]  created & activated \"Predict NIFTY's Open — {label}\" (id={gid})", flush=True)
    except Exception as e:
        print(f"  [games]  failed to create next open-prediction game — {e}", flush=True)


def _run_eod_tasks(daily_alerts: list):
    """
    Run at 16:00 IST after market close.
    Upstox has complete EOD data by then.
    Full sync + tick cleanup + expiry cache refresh.
    """
    from sync.daily_sync import run_daily_sync
    from db.queries import cleanup_ticks

    now = _ist_now()
    print(f"\n[{now.strftime('%H:%M IST')}]  ── EOD tasks ───────────────────────────────────")

    print("\nRunning end-of-day Upstox sync...\n")
    try:
        run_daily_sync()
    except Exception as e:
        print(f"  [EOD sync failed]  {e}", flush=True)

    print("Resolving today's NIFTY close-prediction game and opening tomorrow's...")
    _run_eod_game_tasks()

    print("Cleaning up old ticks (>7 days)...")
    try:
        deleted = cleanup_ticks(days_to_keep=7)
        print(f"  Deleted {deleted} tick row(s).\n", flush=True)
    except Exception as e:
        print(f"  [tick cleanup failed]  {e}", flush=True)

    print("Refreshing option expiry dates and F&O instruments from Upstox...")
    try:
        expiry_cache.refresh()
    except Exception as e:
        print(f"  [expiry refresh failed]  {e}", flush=True)
    try:
        from live.fo_instruments import refresh as refresh_fo
        refresh_fo(force=True)   # force re-download at EOD so tomorrow's cache is fresh
        print()
    except Exception as e:
        print(f"  [F&O instruments refresh failed]  {e}", flush=True)

    print(f"[{_ist_now().strftime('%H:%M IST')}]  ── EOD tasks complete ──────────────────────\n")


# ---------------------------------------------------------------------------
# Trigger builder
# ---------------------------------------------------------------------------

def _expand_symbols(sym_cfg) -> list[str]:
    all_names = [s["name"] for s in SYMBOLS]
    if sym_cfg == "all":
        return all_names
    return [n for n in sym_cfg if n in all_names]


def _build_all_triggers() -> tuple[dict[str, list[BaseTrigger]], list[str], dict[str, str]]:
    """
    Returns:
        ikey_triggers : {instrument_key: [triggers]}
        ikeys         : deduplicated instrument keys to poll
        ikey_to_name  : {instrument_key: symbol_name}
    """
    ikey_triggers: dict[str, list[BaseTrigger]] = {}
    ikey_to_name:  dict[str, str]               = {}

    print(f"Loading {len(TRIGGERS)} trigger(s)...\n")

    for cfg in TRIGGERS:
        for sym_name in _expand_symbols(cfg.get("symbols", "all")):
            ikey = UPSTOX_INSTRUMENT_KEYS.get(sym_name)
            if not ikey:
                print(f"  skip  {sym_name}  [{cfg['name']}]  — no UPSTOX_INSTRUMENT_KEYS entry")
                continue

            trig = build_trigger(cfg, sym_name)
            try:
                trig.refresh()
            except Exception as e:
                print(f"  skip  {sym_name}  [{cfg['name']}]  — {e}")
                continue

            summary = trig.summary() if hasattr(trig, "summary") else ""
            print(f"  ok    {sym_name:<14}  [{cfg['name']}]  {summary}")

            ikey_triggers.setdefault(ikey, []).append(trig)
            ikey_to_name[ikey] = sym_name

    # Poll every configured symbol even when no trigger references it (e.g.
    # TRIGGERS is empty) — tick storage, candle building, the price cache and
    # the EOD sync all key off this set, not just alerting. Without this an
    # empty TRIGGERS made ikeys empty and run_live() returned right after startup.
    for sym in SYMBOLS:
        ikey = UPSTOX_INSTRUMENT_KEYS.get(sym["name"])
        if ikey and ikey not in ikey_to_name:
            ikey_to_name[ikey] = sym["name"]
            ikey_triggers.setdefault(ikey, [])
            print(f"  ok    {sym['name']:<14}  [no triggers — data collection only]")

    return ikey_triggers, list(ikey_triggers.keys()), ikey_to_name


# ---------------------------------------------------------------------------
# Main poll loop
# ---------------------------------------------------------------------------

def run_live(force: bool = False):
    now = _ist_now()
    print(f"\n{'='*54}")
    print(f"  Drishti — Live Poller")
    print(f"  {now.strftime('%Y-%m-%d  %H:%M IST')}")
    print(f"{'='*54}\n")

    if not force:
        check_or_exit()
        print()

    _run_startup_tasks()

    ikey_triggers, ikeys, ikey_to_name = _build_all_triggers()

    # One watcher per intraday timeframe — fires once at each candle close
    _INTRADAY_TF = [("1m", 1), ("5m", 5), ("15m", 15), ("1h", 60)]
    watchers = {key: CandleWatcher(mins) for key, mins in _INTRADAY_TF}
    for w in watchers.values():
        w.mark_startup()

    # Separate 5-min timer for option-chain snapshot capture. Deliberately its
    # own CandleWatcher instance (not the "5m" candle watcher above) — sharing
    # would mean whichever caller checks should_build() first consumes that
    # boundary's single True, starving the other. Fully independent of
    # candle-building / ticks / price_cache; feeds only option_chain_5m.
    option_chain_watcher = CandleWatcher(5)
    option_chain_watcher.mark_startup()

    if not ikeys:
        print("\nNo triggers active. Check TRIGGERS and UPSTOX_INSTRUMENT_KEYS in config.py")
        return

    tick_store.init(ikey_to_name)
    all_symbol_names = list(ikey_to_name.values())

    _spot_ikeys = list(SPOT_IKEYS.values())

    total = sum(len(v) for v in ikey_triggers.values())
    print(f"\n{total} trigger(s) active across {len(ikeys)} symbol(s)"
          f" — polling every {POLL_INTERVAL_SECONDS}s\n")

    # Morning brief, pre-market analysis and EOD brief were removed 2026-09-22 — the poller now
    # only waits for the market to open (no scheduled Telegram messages).
    if not force:
        # Fires at GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST (09:00), 15min BEFORE
        # market open — a deliberate safety margin, not the market-open
        # moment itself, so nobody can snipe a last-second open-guess once
        # NIFTY has effectively already started printing. _wait_until() is
        # a no-op if the process starts after 09:00 (e.g. a late restart).
        _wait_until(*GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST)
        _run_market_open_game_tasks()
        wait_for_market_open()

    error_streak = 0
    daily_alerts: list[dict] = []   # accumulates every signal fired today
    chain_triggers_thread: threading.Thread | None = None   # background run — see below
    _poll_count  = 0                # periodic GC counter
    _close_entries_done = False     # fires once, when the clock crosses market close
    _close_entry_cutoff_minutes = GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST[0] * 60 + GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST[1]

    while force or is_market_open():
        # Candle close: build from ticks → refresh triggers for that timeframe
        for tf_key, watcher in watchers.items():
            if not watcher.should_build():
                continue
            t = _ist_now()
            print(f"\n[{t.strftime('%H:%M IST')}]  {tf_key} candle closed — building from ticks...",
                  flush=True)
            candle_builder.build_all(all_symbol_names, tf_key)
            for triggers in ikey_triggers.values():
                for trig in triggers:
                    if trig.timeframe != tf_key:
                        continue
                    try:
                        trig.refresh()
                    except Exception as e:
                        print(f"  [refresh failed — {trig.symbol} {trig.name}]  {e}",
                              flush=True)
            print("  Done.\n", flush=True)

        # 5-min option-chain snapshot capture — own fetch mechanism (option-chain
        # endpoint, not per-instrument LTP), fully separate from _all_ikeys below.
        if option_chain_watcher.should_build():
            try:
                option_chain_capture.run_capture()
            except Exception as e:
                print(f"  [option chain capture failed]  {e}", flush=True)

            # run_chain_triggers() used to run inline, right here, blocking this loop.
            # Confirmed 2026-09-22 (prod log): a slow evaluation cycle (~2 min, before the
            # get_ltp/get_merged_cadence_dates dedup+index fixes) stalled the ENTIRE poller
            # for that whole time — no LTP polls, no ticks recorded, no candles built,
            # visible as "only 0 tick(s) — skipped" on the next candle close. Those fixes
            # make a normal cycle fast, but nothing guarantees every future cycle stays
            # fast (Upstox rate-limiting, DB growth, a network hiccup) — so this now runs
            # in a background thread instead, and a still-running previous thread means
            # this cycle's run is skipped rather than stacking up concurrent evaluations.
            if chain_triggers_thread is not None and chain_triggers_thread.is_alive():
                print("  [chain triggers]  previous run still in progress — skipping this cycle", flush=True)
            else:
                chain_triggers_thread = threading.Thread(
                    target=_run_chain_triggers_safe, name="chain-triggers", daemon=True
                )
                chain_triggers_thread.start()

        # Build full key list: trigger instruments + spot indices + open trade legs
        try:
            _trade_ikeys = get_open_trade_ikeys()
        except Exception:
            _trade_ikeys = []
        _all_ikeys = list(set(ikeys + _spot_ikeys + _trade_ikeys))

        # Fetch LTPs
        try:
            prices = get_ltp(_all_ikeys)
            error_streak = 0
        except RuntimeError as e:
            print(f"\nFatal: {e}")
            return
        except Exception as e:
            error_streak += 1
            print(f"  [{_ist_now().strftime('%H:%M:%S')}]  poll error ({error_streak}): {e}",
                  flush=True)
            if error_streak >= 5:
                print("5 consecutive poll failures — stopping.")
                return
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        # Write all prices (trigger + spot + trade legs) to shared price cache
        try:
            update_price_cache(prices)
        except Exception as e:
            print(f"  [price cache update failed]  {e}", flush=True)

        # Tick store only needs trigger-instrument prices
        tick_store.record({k: v for k, v in prices.items() if k in ikey_to_name})

        # Once per day, the moment the clock crosses GAME_NIFTY_CLOSE_ENTRY_
        # CUTOFF_IST (15:00, a safety margin before NIFTY's real/effective
        # 15:15 close): stop taking entries on today's NIFTY close-
        # prediction game. Skipped under --force — that's for testing
        # outside real market hours, not for touching real games.
        if not force and not _close_entries_done and _ist_minutes() >= _close_entry_cutoff_minutes:
            _close_entries_done = True
            _run_close_entry_cutoff_task()

        for ikey, ltp in prices.items():
            for trig in ikey_triggers.get(ikey, []):
                result = trig.check(ltp)
                if not result:
                    continue
                sigs = result if isinstance(result, list) else [result]
                for signal in sigs:
                    send_alert(signal)
                    daily_alerts.append(signal)

        _poll_count += 1
        if _poll_count % 120 == 0:   # every ~10 min (120 × 5s)
            gc.collect()

        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"\n[{_ist_now().strftime('%H:%M IST')}]  Market closed (15:30 IST). Polling stopped.")

    # Keep price cache live until 16:00 IST — NSE call-auction settles after 15:30
    # and Upstox continues to serve updated LTPs during the closing session.
    # Triggers and tick store are off; only price_cache is updated.
    if not force and _ist_minutes() < 16 * 60:
        print(f"[{_ist_now().strftime('%H:%M IST')}]  Post-close cache update — polling every 30s until 16:00 IST...",
              flush=True)
        while _ist_minutes() < 16 * 60:
            try:
                _trade_ikeys = get_open_trade_ikeys()
            except Exception:
                _trade_ikeys = []
            _post_ikeys = list(set(ikeys + _spot_ikeys + _trade_ikeys))
            try:
                prices = get_ltp(_post_ikeys)
                update_price_cache(prices)
            except Exception as e:
                print(f"  [post-close cache update]  {e}", flush=True)
            time.sleep(30)

    # EOD tasks at 16:00 — Upstox data is reliable by then
    # Skipped on --force (testing) since market didn't actually close
    if not force:
        _run_eod_tasks(daily_alerts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drishti live poller")
    parser.add_argument("--force", action="store_true",
                        help="Skip market-hours and holiday check (for testing)")
    args = parser.parse_args()
    run_live(force=args.force)
