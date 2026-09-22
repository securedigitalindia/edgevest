"""
Drishti — Live Poller
=====================
Run:
    python poller.py live
    python poller.py live --force    # skip market-hours + holiday check (for testing)

Daily lifecycle:
  Startup   : holiday check → expiry cache refresh → build triggers
  09:15 IST : first tick — resolve yesterday evening's NIFTY open-prediction
              game, open today's NIFTY close-prediction game
  Market hrs: poll every 5s → store ticks → run triggers → build 1h candles at :15 boundary
  16:00 IST : daily Upstox sync → resolve today's NIFTY close-prediction game,
              open tomorrow's NIFTY open-prediction game → tick cleanup →
              expiry cache refresh → exit
  (see docs/prd/nifty-daily-prediction-games.md for the games themselves)
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
    get_active_auto_game, create_game, set_game_status, resolve_game,
    get_system_user_id,
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


def _run_market_open_game_tasks(nifty_open_ltp: float):
    """
    Called once, on the first tick after the market opens (see the
    `_market_open_game_tasks_done` guard in the poll loop below). Two
    independent steps chained by timing, not by outcome — either can fail
    on its own without blocking the other:
      1. Close + resolve last evening's "predict NIFTY's open" game using
         this first tick as the actual open.
      2. Create + activate today's "predict NIFTY's close" game.
    See docs/prd/nifty-daily-prediction-games.md.
    """
    try:
        game = get_active_auto_game("nifty_next_open")
        if game:
            set_game_status(game["id"], "closed")
            resolve_game(game["id"], result_value=str(nifty_open_ltp),
                         win_threshold=GAME_NIFTY_OPEN_WIN_THRESHOLD)
            print(f"  [games]  resolved '{game['title']}' — open={nifty_open_ltp}", flush=True)
        else:
            print("  [games]  no pending open-prediction game to resolve "
                  "(none created last evening?)", flush=True)
    except Exception as e:
        print(f"  [games]  failed to resolve open-prediction game — {e}", flush=True)

    try:
        if get_active_auto_game("nifty_today_close"):
            print("  [games]  today's close-prediction game already exists — skipping create", flush=True)
            return
        today = _ist_now()
        label = today.strftime("%a, %d %b %Y")
        close_at = today.replace(hour=MARKET_CLOSE_IST[0], minute=MARKET_CLOSE_IST[1],
                                  second=0, microsecond=0)
        gid = create_game(
            title=f"Predict NIFTY's Close — {label}",
            description=f"Guess where NIFTY 50 closes today ({label}). Closest guess within "
                        f"{GAME_NIFTY_CLOSE_WIN_THRESHOLD} points of the actual close wins "
                        f"{GAME_NIFTY_CLOSE_REWARD_POOL} credits — no winner if nobody's close enough.",
            game_type="price_prediction", symbol="NIFTY50",
            start_time=_utc_iso(today), end_time=_utc_iso(close_at),
            reward_pool=GAME_NIFTY_CLOSE_REWARD_POOL, winner_count=1,
            initial_cash=1_000_000, created_by=get_system_user_id(),
            auto_kind="nifty_today_close",
        )
        set_game_status(gid, "active")
        print(f"  [games]  created & activated \"Predict NIFTY's Close — {label}\" (id={gid})", flush=True)
    except Exception as e:
        print(f"  [games]  failed to create today's close-prediction game — {e}", flush=True)


def _run_eod_game_tasks():
    """
    Called from _run_eod_tasks(), after the Upstox EOD sync — candles_1d has
    today's official close by then. Same chained pattern as
    _run_market_open_game_tasks(), mirrored for the other side of the day:
      1. Close + resolve today's "predict NIFTY's close" game using the
         official daily close (not a raw LTP snapshot — more accurate, and
         the sync just made it final).
      2. Create + activate a "predict NIFTY's open" game for the next
         trading day (may be several days out over a weekend/holiday block).
    See docs/prd/nifty-daily-prediction-games.md.
    """
    try:
        game = get_active_auto_game("nifty_today_close")
        if game:
            candles = get_candles("NIFTY50", "1d", limit=1)
            if candles.empty:
                print("  [games]  no NIFTY50 daily candle available yet — leaving close-prediction "
                      "game unresolved this cycle", flush=True)
            else:
                actual_close = float(candles.iloc[-1]["close"])
                set_game_status(game["id"], "closed")
                resolve_game(game["id"], result_value=str(actual_close),
                             win_threshold=GAME_NIFTY_CLOSE_WIN_THRESHOLD)
                print(f"  [games]  resolved '{game['title']}' — close={actual_close}", flush=True)
        else:
            print("  [games]  no pending close-prediction game to resolve "
                  "(none created this morning?)", flush=True)
    except Exception as e:
        print(f"  [games]  failed to resolve close-prediction game — {e}", flush=True)

    try:
        if get_active_auto_game("nifty_next_open"):
            print("  [games]  next open-prediction game already exists — skipping create", flush=True)
            return
        now = _ist_now()
        target = next_trading_day(now.date())
        label = target.strftime("%a, %d %b %Y")
        open_at = now.replace(year=target.year, month=target.month, day=target.day,
                              hour=MARKET_OPEN_IST[0], minute=MARKET_OPEN_IST[1],
                              second=0, microsecond=0)
        gid = create_game(
            title=f"Predict NIFTY's Open — {label}",
            description=f"Guess where NIFTY 50 opens on {label}. Closest guess within "
                        f"{GAME_NIFTY_OPEN_WIN_THRESHOLD} points of the actual open wins "
                        f"{GAME_NIFTY_OPEN_REWARD_POOL} credits — no winner if nobody's close enough. "
                        f"Entries close the moment the market opens.",
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
        wait_for_market_open()

    error_streak = 0
    daily_alerts: list[dict] = []   # accumulates every signal fired today
    chain_triggers_thread: threading.Thread | None = None   # background run — see below
    _poll_count  = 0                # periodic GC counter
    _market_open_game_tasks_done = False   # fires once, on the first tick with a NIFTY50 LTP
    _nifty_ikey = UPSTOX_INSTRUMENT_KEYS.get("NIFTY50")

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

        # Once per day, on the first tick that actually has a NIFTY50 price:
        # resolve last evening's open-prediction game and open today's
        # close-prediction game. Skipped under --force — that's for testing
        # outside real market hours, not for creating real games.
        if not force and not _market_open_game_tasks_done:
            _nifty_ltp = prices.get(_nifty_ikey)
            if _nifty_ltp is not None:
                _market_open_game_tasks_done = True
                _run_market_open_game_tasks(_nifty_ltp)

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
