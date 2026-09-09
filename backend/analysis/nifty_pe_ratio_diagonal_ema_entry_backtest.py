"""
NIFTY PE ratio diagonal spread — systematic EMA20/EMA50 entry backtest.

Builds on the diagonal-spread shape already established in
nifty_pe_ratio_diagonal_simulator.py / _v2.py (BUY 1x current-expiry PE,
SELL 2x next-expiry PE, 400pt gap) but replaces the fixed 24100/24000/23900
strike list with a systematic, signal-driven entry rule given directly by
the user:

ENTRY SIGNAL (evaluated on NIFTY FUT 5-min candle closes, continuously):
    Track EMA20 and EMA50. Whenever EMA20 < EMA50 (a mild downtrend
    regime) AND price crosses UP through EMA50 (previous candle's close
    below EMA50, this candle's close at/above it — a bounce touching the
    falling 50-EMA from underneath) -> fire an entry. Mirrors
    live/triggers.py's EmaCrossTrigger cross-detection exactly
    (curr_above = close > ema; fires when curr_above != prev_above),
    just evaluated on close-of-5-min-candle here instead of live LTP.
    No de-dup, no exit rule (none given yet) — every occurrence fires a
    fresh, independent entry; this script reports every entry taken and
    the resulting net open position, it doesn't close anything.

EXPIRY-LEG SELECTION (evaluated fresh per signal, using the calendar date
of the signal candle):
    nearest = first expiry (from the merged weekly+monthly date list)
              strictly after the signal date.
    DTE = (nearest - signal_date).days
    DTE <= 1  -> leg1_expiry = expiry AFTER nearest, leg2_expiry = the one after that
                 (skip `nearest` entirely — 0 or 1 day out is too close to trade)
    DTE >  1  -> leg1_expiry = nearest, leg2_expiry = the one after that

STRIKE SELECTION, at the signal candle's futures close `F`:
    leg1_strike (BUY 1x PE)  = floor(F / 100) * 100   (nearest 100-multiple at/below F)
    leg2_strike (SELL 2x PE) = leg1_strike - 400

Entry premiums are the actual PE LTP at the signal candle's own timestamp,
pulled from Upstox's History API per-instrument (no local DB price reads —
same posture as v2's historical replay).

Data: NIFTY FUT 5-min candles, historical (Upstox History API, capped at
30 days back) + today's in-progress/closed session (Upstox's intra-day
candle endpoint, which has no historical-lookback equivalent) stitched
into one continuous close series. `--warmup-days` of candles before
--from-date are pulled purely to seed EMA20/EMA50 — no signals are
evaluated in that window.

Usage:
    cd backend && source venv/bin/activate
    python analysis/nifty_pe_ratio_diagonal_ema_entry_backtest.py \
        --from-date 2026-09-01 --export-json /tmp/ema_entry_backtest.json
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pandas_ta as ta

from live.holidays import is_trading_day
from db.queries import get_merged_cadence_dates, get_candles
from config import UPSTOX_INSTRUMENT_KEYS
from nifty_fut_ref import (
    resolve_front_month_future, fetch_candles_utc, fetch_intraday_candles_utc,
    resolve_pe_instrument_keys, nearest_price, IST,
)

SYMBOL = "NIFTY50"
EMA_FAST = 20
EMA_SLOW = 50
LEG_GAP = 400
STRIKE_STEP = 100


def build_fut_series(fut_ikey: str, warmup_start: str, hist_end: str) -> dict:
    """Futures close lookup, historical [warmup_start, hist_end] + today's intraday — used only to
    read off the futures price at a given signal timestamp for strike selection (see module docstring
    on why strikes/entry pricing stay on the future even though the EMA signal itself is now on spot)."""
    hist = fetch_candles_utc(fut_ikey, warmup_start, hist_end) if hist_end >= warmup_start else {}
    today = fetch_intraday_candles_utc(fut_ikey)
    return {**hist, **today}


def build_spot_series(hist_end: str, fallback_warmup_start: str) -> pd.DataFrame:
    """
    NIFTY50 spot/index close series for EMA20/EMA50 — sourced from the local
    DB's `candles_5m` table first (6+ months of history there as of
    2026-09, vs. Upstox's History API 30-day cap for 5-min data — a much
    longer, more reliable EMA warm-up than pulling from Upstox alone), then
    Upstox-direct to cover what the DB doesn't have: History API for any
    gap between the DB's last row and yesterday (e.g. a stretch where the
    poller wasn't running), + the intraday endpoint for today (the DB never
    has today's candles from a completed run). Uses the ENTIRE available DB
    history as EMA warm-up, not just a fixed lookback window — the more
    genuine history behind EMA20/50, the less sensitive the crossover
    detection is to where the warm-up window happens to start.
    """
    spot_ikey = UPSTOX_INSTRUMENT_KEYS["NIFTY50"]
    db_df = get_candles("NIFTY50", "5m", limit=100000)
    db_lookup = {}
    if not db_df.empty:
        db_lookup = {
            ts.strftime("%Y-%m-%dT%H:%M:%SZ"): close
            for ts, close in zip(db_df["ts"], db_df["close"])
        }
        db_last_date = max(db_lookup)[:10]
    else:
        db_last_date = None

    # Gap-fill from the day after the DB's last row (or a fallback lookback
    # if the DB has nothing at all) through yesterday, via Upstox History API.
    gap_start = (date.fromisoformat(db_last_date) + timedelta(days=1)).isoformat() if db_last_date else fallback_warmup_start
    gap_lookup = fetch_candles_utc(spot_ikey, gap_start, hist_end) if hist_end >= gap_start else {}
    today_lookup = fetch_intraday_candles_utc(spot_ikey)

    merged = {**db_lookup, **gap_lookup, **today_lookup}
    if not merged:
        raise RuntimeError("No spot candles returned at all — check UPSTOX_ACCESS_TOKEN / candles_5m population.")
    ts_sorted = sorted(merged)
    df = pd.DataFrame({"ts": ts_sorted, "close": [merged[t] for t in ts_sorted]})
    df["ema20"] = ta.ema(df["close"], length=EMA_FAST)
    df["ema50"] = ta.ema(df["close"], length=EMA_SLOW)
    print(f"Spot series sources: DB candles_5m through {db_last_date or 'n/a'} ({len(db_lookup)} rows), "
          f"Upstox gap-fill {gap_start}..{hist_end} ({len(gap_lookup)} rows), "
          f"Upstox intraday today ({len(today_lookup)} rows)")
    return df


def resolve_expiry_legs(signal_date: str, merged_expiries: list[str]) -> tuple[str, str, int]:
    upcoming = [e for e in merged_expiries if e > signal_date]
    if len(upcoming) < 3:
        raise ValueError(f"Not enough future expiries for signal_date={signal_date}: {merged_expiries}")
    nearest = upcoming[0]
    dte = (date.fromisoformat(nearest) - date.fromisoformat(signal_date)).days
    if dte <= 1:
        return upcoming[1], upcoming[2], dte  # skip `nearest` entirely
    return upcoming[0], upcoming[1], dte


def find_signals(df: pd.DataFrame, from_date: str) -> list[dict]:
    """
    Walk the merged SPOT close series chronologically. EMA needs both
    fast/slow values (NaN during warm-up) to evaluate; the regime+cross
    rule is only ever checked from --from-date onward, but prev_above's
    baseline can come from a candle before that date (continuous tracking,
    no reset).
    """
    signals = []
    prev_above = None
    for i in range(len(df)):
        row = df.iloc[i]
        if pd.isna(row["ema50"]) or pd.isna(row["ema20"]):
            continue
        curr_above = row["close"] > row["ema50"]
        if prev_above is None:
            prev_above = curr_above
            continue
        crossed_up = curr_above and not prev_above
        prev_above = curr_above
        if not crossed_up:
            continue
        if row["ts"][:10] < from_date:
            continue
        if not (row["ema20"] < row["ema50"]):
            continue  # regime filter: EMA20 must be below EMA50 at the moment of the cross
        signals.append({
            "ts": row["ts"], "spot": float(row["close"]),
            "ema20": round(float(row["ema20"]), 2), "ema50": round(float(row["ema50"]), 2),
        })
    return signals


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-date", default="2026-09-01", help="first calendar day signals are evaluated on")
    ap.add_argument("--warmup-days", type=int, default=20,
                     help="fallback trading-day lookback for the futures price lookup and for spot "
                          "only if candles_5m has no NIFTY50 rows at all; spot's real EMA warm-up "
                          "uses the DB's full available history instead")
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--lot-size", type=int, default=None)
    ap.add_argument("--export-json", default=None)
    args = ap.parse_args()

    merged_expiries = get_merged_cadence_dates(args.symbol)
    if len(merged_expiries) < 3:
        print(f"Not enough expiry history to resolve leg pairs: {merged_expiries}")
        sys.exit(1)

    fut = resolve_front_month_future("NIFTY")
    lot_size = args.lot_size or fut["lot_size"]

    from_d = date.fromisoformat(args.from_date)
    warmup_start = from_d
    trading_days_back = 0
    while trading_days_back < args.warmup_days:
        warmup_start -= timedelta(days=1)
        if is_trading_day(warmup_start):
            trading_days_back += 1

    today_ist = datetime.now(timezone.utc).astimezone(IST).date()
    hist_end = today_ist - timedelta(days=1)
    while not is_trading_day(hist_end):
        hist_end -= timedelta(days=1)

    print(f"Futures: {fut['trading_symbol']}  lot_size={lot_size}  (used only for strike selection / entry pricing)")
    print(f"Building NIFTY50 SPOT series for EMA{EMA_FAST}/EMA{EMA_SLOW} (the signal itself) ...")
    spot_df = build_spot_series(hist_end.isoformat(), warmup_start.isoformat())
    print(f"Spot series: {len(spot_df)} candles, {spot_df['ts'].iloc[0]} .. {spot_df['ts'].iloc[-1]}")

    print(f"Fetching futures {warmup_start} .. {hist_end} + today's intraday, for strike selection ...")
    fut_lookup = build_fut_series(fut["instrument_key"], warmup_start.isoformat(), hist_end.isoformat())

    signals = find_signals(spot_df, args.from_date)
    print(f"\n{len(signals)} entry signal(s) found from {args.from_date} onward:\n")
    if not signals:
        print("No signals — nothing further to report.")
        return

    # Resolve expiry legs + strikes for every signal up front, so PE
    # instrument-key resolution can be batched once per unique expiry
    # rather than once per signal.
    for sig in signals:
        sig_date = sig["ts"][:10]
        leg1_exp, leg2_exp, dte = resolve_expiry_legs(sig_date, merged_expiries)
        fut_at_signal = nearest_price(fut_lookup, sig["ts"])
        if fut_at_signal is None:
            raise RuntimeError(f"No futures price available near {sig['ts']} for strike selection.")
        leg1_strike = (fut_at_signal // STRIKE_STEP) * STRIKE_STEP
        leg2_strike = leg1_strike - LEG_GAP
        sig.update(leg1_expiry=leg1_exp, leg2_expiry=leg2_exp, dte_at_signal=dte,
                   fut_at_signal=fut_at_signal, leg1_strike=leg1_strike, leg2_strike=leg2_strike)

    strikes_by_expiry: dict[str, set] = {}
    for sig in signals:
        strikes_by_expiry.setdefault(sig["leg1_expiry"], set()).add(sig["leg1_strike"])
        strikes_by_expiry.setdefault(sig["leg2_expiry"], set()).add(sig["leg2_strike"])

    ikeys_by_expiry_strike: dict[tuple[str, float], str] = {}
    for expiry, strikes in strikes_by_expiry.items():
        resolved = resolve_pe_instrument_keys(args.symbol, expiry, strikes)
        for k, ik in resolved.items():
            ikeys_by_expiry_strike[(expiry, k)] = ik
        missing = strikes - set(resolved)
        if missing:
            print(f"Warning: no PE contract found for {expiry} strikes {sorted(missing)}")

    # Historical candles for every distinct instrument actually needed —
    # one call per instrument, covering the whole backtest window.
    candle_cache: dict[str, dict] = {}
    for (expiry, k), ik in ikeys_by_expiry_strike.items():
        hist = fetch_candles_utc(ik, warmup_start.isoformat(), hist_end.isoformat())
        today_c = fetch_intraday_candles_utc(ik)
        candle_cache[ik] = {**hist, **today_c}

    entries = []
    for sig in signals:
        l1_ik = ikeys_by_expiry_strike.get((sig["leg1_expiry"], sig["leg1_strike"]))
        l2_ik = ikeys_by_expiry_strike.get((sig["leg2_expiry"], sig["leg2_strike"]))
        l1_ltp = nearest_price(candle_cache.get(l1_ik, {}), sig["ts"]) if l1_ik else None
        l2_ltp = nearest_price(candle_cache.get(l2_ik, {}), sig["ts"]) if l2_ik else None
        if l1_ltp is None or l2_ltp is None:
            print(f"{sig['ts']}  spot={sig['spot']:.1f} fut={sig['fut_at_signal']:.1f}  "
                  f"-- missing PE premium data, skipping this entry --")
            continue
        debit = round(l1_ltp - 2 * l2_ltp, 2)
        entry = {
            **sig, "leg1_ltp": l1_ltp, "leg2_ltp": l2_ltp, "entry_debit": debit,
        }
        entries.append(entry)
        print(f"{sig['ts']}  spot={sig['spot']:.1f}  fut={sig['fut_at_signal']:.1f}  "
              f"ema20(spot)={sig['ema20']}  ema50(spot)={sig['ema50']}  "
              f"DTE@nearest={sig['dte_at_signal']}")
        print(f"    BUY  1x {sig['leg1_strike']:.0f}PE ({sig['leg1_expiry']}) @ {l1_ltp}")
        print(f"    SELL 2x {sig['leg2_strike']:.0f}PE ({sig['leg2_expiry']}) @ {l2_ltp}")
        print(f"    net entry debit = {debit}  ({'credit' if debit < 0 else 'debit'} to open)\n")

    # ---- Final net open position (no exits modeled — every entry stays open) ----
    net: dict[tuple[str, float, str], float] = {}  # (expiry, strike, side) -> net lots
    for e in entries:
        net[(e["leg1_expiry"], e["leg1_strike"], "BUY")] = net.get((e["leg1_expiry"], e["leg1_strike"], "BUY"), 0) + 1
        net[(e["leg2_expiry"], e["leg2_strike"], "SELL")] = net.get((e["leg2_expiry"], e["leg2_strike"], "SELL"), 0) + 2

    # Mark-to-market at the latest close for every leg still open — bounded
    # by the futures/options data (fut_lookup), not the spot series, since
    # that's what the option/futures candle_cache actually has prices for.
    last_ts = max(fut_lookup)
    mtm_rows = []
    total_pnl_rs = 0.0
    for (expiry, strike, side), lots in net.items():
        ik = ikeys_by_expiry_strike.get((expiry, strike))
        cur_ltp = nearest_price(candle_cache.get(ik, {}), last_ts) if ik else None
        entry_ltps = [e["leg1_ltp"] if (e["leg1_expiry"], e["leg1_strike"]) == (expiry, strike) and side == "BUY"
                      else e["leg2_ltp"] if (e["leg2_expiry"], e["leg2_strike"]) == (expiry, strike) and side == "SELL"
                      else None for e in entries]
        entry_ltps = [v for v in entry_ltps if v is not None]
        avg_entry = round(sum(entry_ltps) / len(entry_ltps), 2) if entry_ltps else None
        pnl_rs = None
        if cur_ltp is not None and avg_entry is not None:
            direction = 1 if side == "BUY" else -1
            pnl_rs = round(direction * (cur_ltp - avg_entry) * lots * lot_size, 2)
            total_pnl_rs += pnl_rs
        mtm_rows.append({
            "expiry": expiry, "strike": strike, "side": side, "lots": lots,
            "avg_entry_ltp": avg_entry, "current_ltp": cur_ltp, "mtm_pnl_rs": pnl_rs,
        })

    mtm_rows.sort(key=lambda r: (r["expiry"], -r["strike"]))
    print("=" * 78)
    print(f"FINAL OPEN POSITION as of {last_ts}  ({len(entries)} entries taken, no exits modeled)")
    print("=" * 78)
    header = f"{'expiry':>10} {'strike':>8} {'side':>5} {'lots':>5} {'avg_entry':>10} {'current':>10} {'mtm_pnl_rs':>12}"
    print(header)
    for r in mtm_rows:
        print(f"{r['expiry']:>10} {r['strike']:>8.0f} {r['side']:>5} {r['lots']:>5.0f} "
              f"{r['avg_entry_ltp'] if r['avg_entry_ltp'] is not None else '--':>10} "
              f"{r['current_ltp'] if r['current_ltp'] is not None else '--':>10} "
              f"{r['mtm_pnl_rs'] if r['mtm_pnl_rs'] is not None else '--':>12}")
    print(f"\nTotal MTM P&L across all open legs: Rs {total_pnl_rs:,.2f}  (lot_size={lot_size})")

    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump({
                "symbol": args.symbol, "from_date": args.from_date, "lot_size": lot_size,
                "fut_trading_symbol": fut["trading_symbol"],
                "as_of_ts": last_ts, "entries": entries,
                "final_position": mtm_rows, "total_mtm_pnl_rs": round(total_pnl_rs, 2),
            }, f, indent=2, default=str)
        print(f"\nExported to {args.export_json}")


if __name__ == "__main__":
    main()
