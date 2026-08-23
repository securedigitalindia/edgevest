"""
Minute-wise CE+PE combo premium viewer — any NSE or BSE F&O index, any expiry.

Straddle:  --gap 0     → CE and PE both at --strike
Strangle:  --gap 100   → CE at strike+gap, PE at strike-gap

Finest granularity available is 1-minute — Upstox's intraday history API
rejects "seconds" units (verified: 400 Bad Request on 5s/30s requests).
True tick data would require the live WebSocket feed, not this REST call.

--expiry picks the contract. Data shown is for --date (defaults to the
expiry date itself) — that day's full session, via Upstox's historical
candle API for past days or the intraday endpoint for today (the
historical endpoint has no same-day data).

Usage:
    python analysis/option_combo_viewer.py --symbol SENSEX --strike 78800 --gap 0 --expiry 2026-08-06
    python analysis/option_combo_viewer.py --symbol NIFTY50 --strike 25000 --gap 100 --expiry 2026-08-11
    python analysis/option_combo_viewer.py --symbol SENSEX --strike 78800 --expiry 2026-08-06 --minutes 30
"""

import argparse
import gzip
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
import upstox_client
from upstox_client.rest import ApiException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import UPSTOX_ACCESS_TOKEN

IST = ZoneInfo("Asia/Kolkata")
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# user-facing symbol -> (exchange, underlying_symbol in Upstox's instrument file)
_SYMBOL_MAP = {
    "NIFTY50":    ("NSE", "NIFTY"),
    "NIFTY":      ("NSE", "NIFTY"),
    "BANKNIFTY":  ("NSE", "BANKNIFTY"),
    "FINNIFTY":   ("NSE", "FINNIFTY"),
    "MIDCPNIFTY": ("NSE", "MIDCPNIFTY"),
    "SENSEX":     ("BSE", "SENSEX"),
    "BANKEX":     ("BSE", "BANKEX"),
}

_INSTRUMENTS_URL = {
    "NSE": "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
    "BSE": "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz",
}
_SEGMENT = {"NSE": "NSE_FO", "BSE": "BSE_FO"}


def _resolve_symbol(symbol: str) -> tuple[str, str]:
    key = symbol.strip().upper()
    if key not in _SYMBOL_MAP:
        raise SystemExit(f"Unknown symbol {symbol!r} — supported: {sorted(_SYMBOL_MAP)}")
    return _SYMBOL_MAP[key]


def _today_cache_path(exchange: str) -> str:
    today = datetime.now(timezone.utc).astimezone(IST).strftime("%Y-%m-%d")
    return os.path.join(_CACHE_DIR, f"{exchange.lower()}_instruments_{today}.json")


def _load_instruments(exchange: str) -> list[dict]:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = _today_cache_path(exchange)
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    print(f"Downloading {exchange} F&O instrument list...", flush=True)
    resp = requests.get(_INSTRUMENTS_URL[exchange], timeout=30)
    resp.raise_for_status()
    instruments = json.loads(gzip.decompress(resp.content))
    with open(cache_path, "w") as f:
        json.dump(instruments, f)
    return instruments


def _resolve_leg(
    instruments: list[dict], exchange: str, underlying_symbol: str,
    expiry: str | None, strike: int, itype: str,
):
    """
    Find the instrument_key for underlying_symbol/strike/CE|PE.
    expiry=None picks the nearest expiry on or after today.
    expiry=YYYY-MM-DD matches an exact expiry — past or future.
    Returns (instrument_key, expiry_date).
    """
    segment = _SEGMENT[exchange]
    candidates = []
    for row in instruments:
        if row.get("segment") != segment:
            continue
        if row.get("underlying_symbol") != underlying_symbol:
            continue
        if row.get("instrument_type") != itype:
            continue
        if round(row.get("strike_price", 0)) != strike:
            continue
        expiry_ms = row.get("expiry")
        if not expiry_ms:
            continue
        exp_date = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).astimezone(IST).date()
        candidates.append((exp_date, row["instrument_key"], row.get("underlying_key")))

    if not candidates:
        raise SystemExit(f"No {underlying_symbol} {strike} {itype} contract found")

    candidates.sort(key=lambda c: c[0])
    if expiry:
        target = datetime.strptime(expiry, "%Y-%m-%d").date()
        for exp_date, ikey, spot_ikey in candidates:
            if exp_date == target:
                return ikey, exp_date, spot_ikey
        raise SystemExit(f"No {underlying_symbol} {strike} {itype} contract for expiry {expiry}")

    today = datetime.now(IST).date()
    future = [c for c in candidates if c[0] >= today]
    if not future:
        raise SystemExit(f"No {underlying_symbol} {strike} {itype} contract with expiry >= today")
    exp_date, ikey, spot_ikey = future[0]
    return ikey, exp_date, spot_ikey


def _fetch_minute_candles(ikey: str, session_date: date) -> list[list]:
    """1-min candles for session_date. Uses intraday endpoint for today
    (historical endpoint has no same-day data), historical endpoint otherwise."""
    cfg = upstox_client.Configuration()
    cfg.access_token = UPSTOX_ACCESS_TOKEN
    api = upstox_client.HistoryV3Api(upstox_client.ApiClient(cfg))
    today = datetime.now(IST).date()
    try:
        if session_date == today:
            resp = api.get_intra_day_candle_data(ikey, "minutes", 1)
        else:
            date_str = session_date.strftime("%Y-%m-%d")
            resp = api.get_historical_candle_data1(ikey, "minutes", 1, date_str, date_str)
    except ApiException as e:
        raise SystemExit(f"Upstox API error {e.status}: {e.reason}")
    return sorted(resp.data.candles or [], key=lambda c: c[0])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", required=True,
                   help="NIFTY50 | BANKNIFTY | FINNIFTY | MIDCPNIFTY | SENSEX | BANKEX")
    p.add_argument("--strike", type=int, required=True, help="Center strike")
    p.add_argument("--gap", type=int, default=0, help="0 = straddle; N = strangle (CE=strike+N, PE=strike-N)")
    p.add_argument("--expiry", default=None, help="YYYY-MM-DD (past or future); default = nearest expiry >= today")
    p.add_argument("--date", default=None,
                   help="YYYY-MM-DD trading session to show; default = the expiry date itself")
    p.add_argument("--minutes", type=int, default=None,
                   help="Trailing window in minutes; default = full session")
    args = p.parse_args()

    exchange, underlying_symbol = _resolve_symbol(args.symbol)
    ce_strike = args.strike + args.gap
    pe_strike = args.strike - args.gap
    label = "STRADDLE" if args.gap == 0 else f"STRANGLE (±{args.gap})"

    instruments = _load_instruments(exchange)
    ce_ikey, expiry_date, spot_ikey = _resolve_leg(instruments, exchange, underlying_symbol, args.expiry, ce_strike, "CE")
    pe_ikey, _, _ = _resolve_leg(instruments, exchange, underlying_symbol, args.expiry, pe_strike, "PE")

    session_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else expiry_date

    print(f"\n{args.symbol} {label} — expiry {expiry_date}, session {session_date}")
    print(f"  CE {ce_strike} ({ce_ikey})")
    print(f"  PE {pe_strike} ({pe_ikey})")
    print(f"  Spot {underlying_symbol} ({spot_ikey})")

    ce_candles = _fetch_minute_candles(ce_ikey, session_date)
    pe_candles = _fetch_minute_candles(pe_ikey, session_date)
    spot_candles = _fetch_minute_candles(spot_ikey, session_date)
    ce_by_ts = {c[0]: c for c in ce_candles}
    pe_by_ts = {c[0]: c for c in pe_candles}
    spot_by_ts = {c[0]: c for c in spot_candles}

    common_ts = sorted(set(ce_by_ts) & set(pe_by_ts))
    if not common_ts:
        raise SystemExit(f"No overlapping candle timestamps for {session_date} between the two legs.")

    if args.minutes:
        last_ts = datetime.fromisoformat(common_ts[-1])
        cutoff = last_ts - timedelta(minutes=args.minutes - 1)
        window = [ts for ts in common_ts if datetime.fromisoformat(ts) >= cutoff]
        print(f"\nLast {args.minutes} min of {session_date} "
              f"(session data through {last_ts.strftime('%H:%M')} IST):\n")
    else:
        window = common_ts
        print(f"\nFull session {session_date} "
              f"({datetime.fromisoformat(window[0]).strftime('%H:%M')}–"
              f"{datetime.fromisoformat(window[-1]).strftime('%H:%M')} IST):\n")

    # Only Open/Close are summed — they're simultaneous snapshots (start/end
    # of the minute) for both legs. High/Low are NOT summed: each leg's
    # intra-minute high/low can occur at a different tick, so CE_high + PE_high
    # is a number neither leg ever actually traded at — not a real combo high.
    header = (f"{'Time':6} {'CE O':>8} {'CE C':>8} {'PE O':>8} {'PE C':>8} | "
              f"{'Combo O':>9} {'Combo C':>9} | {'Spot':>10}")
    print(header)
    print("-" * len(header))
    for ts in window:
        ce = ce_by_ts[ts]
        pe = pe_by_ts[ts]
        spot = spot_by_ts.get(ts)
        t = datetime.fromisoformat(ts).strftime("%H:%M")
        combo_o = ce[1] + pe[1]
        combo_c = ce[4] + pe[4]
        spot_str = f"{spot[4]:10.2f}" if spot else f"{'—':>10}"
        print(f"{t:6} {ce[1]:8.2f} {ce[4]:8.2f} {pe[1]:8.2f} {pe[4]:8.2f} | "
              f"{combo_o:9.2f} {combo_c:9.2f} | {spot_str}")


if __name__ == "__main__":
    main()
