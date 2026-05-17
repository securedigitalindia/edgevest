"""
Drishti — Live Poller
=====================
Run:
    python main.py live
    python main.py live --force    # skip market-hours + holiday check (for testing)

Daily lifecycle:
  Startup   : holiday check → expiry cache refresh → build triggers
  Market hrs: poll every 5s → store ticks → run triggers → build 1h candles at :15 boundary
  16:00 IST : daily yfinance sync → tick cleanup → expiry cache refresh → exit
"""

import argparse
import sys
import os
import time
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
)
from live.upstox_client import get_ltp
from live.triggers import build_trigger, BaseTrigger
from live.alert import send_alert
from live.expiry import expiry_cache
from live.intraday_sync import CandleWatcher
from live import tick_store, candle_builder
from live.holidays import check_or_exit
from live.briefing import send_morning_brief, send_eod_brief
from live.fo_instruments import SPOT_IKEYS
from db.queries import update_price_cache, get_open_trade_ikeys

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
    print("Market not yet open. Waiting for 09:15 IST...\n", flush=True)
    while not is_market_open():
        print(f"  {_ist_now().strftime('%H:%M:%S IST')}  — waiting...", flush=True)
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
    Only refreshes expiry cache — no yfinance sync here because the market
    may already be open and yfinance would return incomplete in-progress candles.
    The EOD sync at 16:00 IST is the right time to sync (market closed by then).
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


def _run_eod_tasks(daily_alerts: list):
    """
    Run at 16:00 IST after market close.
    yfinance has complete EOD data by then.
    Full sync + tick cleanup + expiry cache refresh + EOD brief.
    """
    from sync.daily_sync import run_daily_sync
    from db.queries import cleanup_ticks

    now = _ist_now()
    print(f"\n[{now.strftime('%H:%M IST')}]  ── EOD tasks ───────────────────────────────────")

    print("\nRunning end-of-day yfinance sync...\n")
    try:
        run_daily_sync()
    except Exception as e:
        print(f"  [EOD sync failed]  {e}", flush=True)

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

    print("Sending EOD brief to Telegram...")
    try:
        send_eod_brief(daily_alerts)
    except Exception as e:
        print(f"  [EOD brief failed]  {e}", flush=True)

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

    if not ikeys:
        print("\nNo triggers active. Check TRIGGERS and UPSTOX_INSTRUMENT_KEYS in config.py")
        return

    tick_store.init(ikey_to_name)
    all_symbol_names = list(ikey_to_name.values())

    _spot_ikeys = list(SPOT_IKEYS.values())

    total = sum(len(v) for v in ikey_triggers.values())
    print(f"\n{total} trigger(s) active across {len(ikeys)} symbol(s)"
          f" — polling every {POLL_INTERVAL_SECONDS}s\n")

    # Morning brief — sent after startup tasks so Telegram confirms we're live
    if not force:
        try:
            send_morning_brief()
        except Exception as e:
            print(f"  [morning brief failed]  {e}", flush=True)

        # Daily pre-market analysis at 08:30 IST
        _wait_until(8, 30)
        try:
            from live.daily_analysis import run_daily_analysis
            run_daily_analysis()
        except Exception as e:
            print(f"  [daily analysis failed]  {e}", flush=True)

        wait_for_market_open()

    error_streak = 0
    daily_alerts: list[dict] = []   # accumulates every signal fired today

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

        for ikey, ltp in prices.items():
            for trig in ikey_triggers.get(ikey, []):
                result = trig.check(ltp)
                if not result:
                    continue
                sigs = result if isinstance(result, list) else [result]
                for signal in sigs:
                    send_alert(signal)
                    daily_alerts.append(signal)

        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"\n[{_ist_now().strftime('%H:%M IST')}]  Market closed (15:30 IST). Polling stopped.")

    # EOD tasks at 16:00 — yfinance data is reliable by then
    # Skipped on --force (testing) since market didn't actually close
    if not force:
        _wait_until(16, 0)
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
