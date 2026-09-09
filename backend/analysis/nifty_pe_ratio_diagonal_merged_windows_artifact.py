"""
NIFTY PE+CE ratio diagonal — merged windowed-backtest artifact builder.

Runs BOTH strategies (side="PE" and side="CE") independently within the
SAME set of auto-detected expiry-rollover windows (window boundaries are
symbol-wide, not side-specific — the same find_window_starts() list applies
to both), and builds one artifact showing both sides' own sets/P&L together
per window, plus a third "Combined (PE+CE)" reference line/column — kept
strictly secondary, per user decision 2026-09-09: PE's own and CE's own
realized figures are the primary numbers, never summed into one headline.

This does not replace nifty_pe_ratio_diagonal_windows_artifact.py (the
single-side builder) — that script and its template stay as they are, for
anyone wanting a single-side deep-dive. This is a new, separate artifact.

Usage:
    cd backend && source venv/bin/activate
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_merged_windows_artifact.py \
        --start-date 2026-08-25 --output /tmp/merged_windows_artifact.html
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.queries import get_merged_cadence_dates
from db.init_db import get_connection
from live.expiry import expiry_cache
from nifty_pe_ratio_diagonal_windowed_backtest import find_window_starts, run_window, ist_ts_for, ENTRY_TIME
from nifty_fut_ref import resolve_front_month_future, fetch_candles_utc, fetch_intraday_candles_utc, IST

SYMBOL = "NIFTY50"
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "nifty_pe_ratio_diagonal_merged_windows_template.html")


def _side_sets(res: dict) -> list[dict]:
    """Only sets that actually priced — see the single-side builder's identical guard.
    Each set already carries `current_value` (2026-09-09) — the same 4-leg combo's
    net value at its own last_ts (full natural range, not capped to the window's exit
    boundary) — computed in run_window() before "values" (the full tick series) was
    stripped there; nothing left to add at this layer."""
    if "sets" not in res:
        return []
    return [s for s in res["sets"] if "entry_value" in s]


def _side_pnl_lookup(res: dict) -> dict:
    if "combined_points" not in res:
        return {}
    return {p["ts"]: p["pnl_pts"] for p in res["combined_points"]}


def build_merged_embed(pe_res: dict, ce_res: dict, window_start: str, window_end_ts: str | None,
                        fut_series: dict, lot_size: int) -> dict:
    """Merge one window's PE and CE run_window() results into one embed."""
    pe_pts = _side_pnl_lookup(pe_res)
    ce_pts = _side_pnl_lookup(ce_res)
    all_ts = sorted(set(pe_pts) | set(ce_pts))

    combined = []
    last_pe, last_ce = 0.0, 0.0
    for ts in all_ts:
        f = fut_series.get(ts)
        if f is None:
            continue
        if ts in pe_pts:
            last_pe = pe_pts[ts]
        if ts in ce_pts:
            last_ce = ce_pts[ts]
        total = round(last_pe + last_ce, 2)
        combined.append({
            "ts": ts, "day": ts[:10], "fut": f,
            "pe_pnl_pts": last_pe, "ce_pnl_pts": last_ce, "total_pnl_pts": total,
            "pe_pnl_rs": round(last_pe * lot_size, 2), "ce_pnl_rs": round(last_ce * lot_size, 2),
            "total_pnl_rs": round(total * lot_size, 2),
            "post_exit": window_end_ts is not None and ts >= window_end_ts,
        })

    pre_exit = [p for p in combined if not p["post_exit"]]
    daily_realized = rollup_daily_merged(pre_exit)
    daily_reference = rollup_daily_merged(combined) if window_end_ts is not None else []

    pe_sets = _side_sets(pe_res)
    ce_sets = _side_sets(ce_res)
    all_sets = sorted(pe_sets + ce_sets, key=lambda s: s["trigger_ts"])

    is_bounded = window_end_ts is not None
    pe_realized = pe_res.get("realized_pnl_pts", 0.0) if is_bounded else pe_res.get("latest_pnl_pts", 0.0)
    ce_realized = ce_res.get("realized_pnl_pts", 0.0) if is_bounded else ce_res.get("latest_pnl_pts", 0.0)
    pe_ref = pe_res.get("latest_pnl_pts", 0.0)
    ce_ref = ce_res.get("latest_pnl_pts", 0.0)

    return {
        "entry_date": window_start, "is_bounded": is_bounded,
        "exit_ts": window_end_ts,
        "pe_ok": "combined_points" in pe_res, "ce_ok": "combined_points" in ce_res,
        "pe_realized_pnl_pts": pe_realized, "pe_realized_pnl_rs": round(pe_realized * lot_size, 2),
        "ce_realized_pnl_pts": ce_realized, "ce_realized_pnl_rs": round(ce_realized * lot_size, 2),
        "pe_ref_pnl_pts": pe_ref, "pe_ref_pnl_rs": round(pe_ref * lot_size, 2),
        "ce_ref_pnl_pts": ce_ref, "ce_ref_pnl_rs": round(ce_ref * lot_size, 2),
        "sets": all_sets, "combined": combined,
        "daily_realized": daily_realized, "daily_reference": daily_reference,
    }


def rollup_daily_merged(points: list[dict]) -> list[dict]:
    days = sorted({p["day"] for p in points})
    out = []
    for d in days:
        last = [p for p in points if p["day"] == d][-1]
        out.append({
            "day": d,
            "pe_pnl_pts": last["pe_pnl_pts"], "pe_pnl_rs": last["pe_pnl_rs"],
            "ce_pnl_pts": last["ce_pnl_pts"], "ce_pnl_rs": last["ce_pnl_rs"],
            "total_pnl_pts": last["total_pnl_pts"], "total_pnl_rs": last["total_pnl_rs"],
        })
    return out


def prepare_run_inputs(conn, start_date: str, end_date: str | None, symbol: str,
                        price_source: str) -> dict | None:
    """
    The cheap, shared-across-all-windows setup: resolve end_date, expiry
    cadence history, window boundaries, and the price series every window's
    trigger-scan reads from. Split out from run_merged_windows_backtest()
    2026-09-09 so backend/strategies/service.py (docs/prd/admin-strategies-
    dashboard.md) can call this ONCE per request and then compute only the
    windows it actually needs (via compute_window_embed below) instead of
    every window every time — the settle-once cache's whole point. Returns
    None if there's nothing usable yet (no local data, no trading days in
    range, or fewer than 3 known expiries).
    """
    if end_date is None:
        cur = conn.execute("SELECT MAX(ts) FROM option_chain_5m")
        max_ts = cur.fetchone()[0]
        if not max_ts:
            return None
        end_date = max_ts[:10]

    merged = get_merged_cadence_dates(symbol, include_quarterly=True)
    if len(merged) < 3:
        return None

    window_starts = find_window_starts(start_date, end_date, merged)
    if not window_starts:
        return None

    pad_from = (date.fromisoformat(start_date) - timedelta(days=1)).isoformat()
    pad_to = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()

    if price_source == "fut":
        fut = resolve_front_month_future("NIFTY")
        lot_size = fut["lot_size"]
        price_label = fut["trading_symbol"]
        fut_series = fetch_candles_utc(fut["instrument_key"], pad_from, pad_to)
        # fetch_candles_utc's historical endpoint never includes today's
        # candles (see its own docstring) — merge in today's intraday
        # candles too whenever the requested range actually reaches today.
        # Without this, fut_series (and everything gated on it: the chart,
        # daily_realized — see build_merged_embed's `if f is None: continue`)
        # silently stops one trading day behind the option-chain data it's
        # paired with, even though the stat tiles (pe_realized_pnl_pts etc.,
        # sourced straight from option-chain-only P&L, no fut_series
        # dependency) correctly show through today. Found 2026-09-09 after
        # a prod capture gap made the mismatch obvious (chart stuck on the
        # 8th, tiles already showing the 9th).
        today_ist = datetime.now(timezone.utc).astimezone(IST).date().isoformat()
        if end_date >= today_ist:
            fut_series.update(fetch_intraday_candles_utc(fut["instrument_key"]))
    else:
        # NIFTY50 index closes from local candles_5m — no live Upstox call.
        lot_size = 65  # last-known NIFTY lot size — no live resolution in spot mode
        price_label = f"{symbol} SPOT"
        rows = conn.execute(
            "SELECT ts, close FROM candles_5m WHERE symbol = ? AND ts >= ? AND ts < ? ORDER BY ts",
            (symbol, pad_from, pad_to),
        ).fetchall()
        fut_series = {
            datetime.fromisoformat(ts).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"): close
            for ts, close in rows
        }

    if not fut_series:
        return None

    return {
        "end_date": end_date, "merged": merged, "window_starts": window_starts,
        "fut_series": fut_series, "lot_size": lot_size, "price_label": price_label,
    }


def compute_window_embed(conn, window_start: str, window_end_ts: str | None, merged: list[str],
                          up_move: float, leg_gap: float, fut_series: dict, symbol: str,
                          lot_size: int, strike_multiple: float = 100, initial_gap: float = 0,
                          side: str = "BOTH") -> dict | None:
    """
    One window's PE+CE embed, or None if nothing usable. The actual per-window
    compute unit — shared by run_merged_windows_backtest() (full recompute, CLI/artifact
    use) and service.py's cached path (recompute only for uncached/open windows).

    side (2026-09-09, user-specified — "give it in config directly ... instead
    of later filter"): "PE" | "CE" | "BOTH" (default). A side not selected is
    never computed at all (skipped, not just hidden) — its run_window() call
    is simply not made, so a real DB-read/compute cost is actually avoided,
    not just filtered client-side after the fact. build_merged_embed() already
    treats an empty {} the same way it treats a genuinely-failed run_window()
    result (no "combined_points" key -> pe_ok/ce_ok false, empty sets/series),
    so no other reshaping is needed here.
    """
    pe_res = (run_window(conn, window_start, window_end_ts, merged, up_move, leg_gap, fut_series, symbol,
                          side="PE", strike_multiple=strike_multiple, initial_gap=initial_gap)
              if side in ("PE", "BOTH") else {})
    ce_res = (run_window(conn, window_start, window_end_ts, merged, up_move, leg_gap, fut_series, symbol,
                          side="CE", strike_multiple=strike_multiple, initial_gap=initial_gap)
              if side in ("CE", "BOTH") else {})
    if "combined_points" not in pe_res and "combined_points" not in ce_res:
        return None
    return build_merged_embed(pe_res, ce_res, window_start, window_end_ts, fut_series, lot_size)


def run_merged_windows_backtest(start_date: str, end_date: str | None, up_move: float, leg_gap: float,
                                 symbol: str = SYMBOL, price_source: str = "fut",
                                 strike_multiple: float = 100, initial_gap: float = 0,
                                 side: str = "BOTH") -> dict | None:
    """
    Pure compute — no argparse/print/sys.exit/file I/O — extracted from main()
    2026-09-09 so backend/strategies/registry.py (docs/prd/admin-strategies-dashboard.md)
    can call the exact same compute path the CLI/artifact uses, with no
    behavioral drift between the two. Always recomputes every window (no
    caching) — for the settle-once-cache path, see service.py, which calls
    prepare_run_inputs()/compute_window_embed() directly instead of this.
    Returns the dict main() used to JSON-dump for __DATA_PLACEHOLDER__ (plus
    start_date/end_date), or None if there's no usable result — the caller
    decides how to surface that (main() prints+exits; the strategy provider
    raises).

    price_source: "fut" (default, live Upstox front-month future — the only
    mode the strategy PRD endorses for real use) or "spot" (local candles_5m
    NIFTY50 index closes, no live Upstox call — kept only as the 2026-09-09
    comparison mode; rejected as a substitute for real runs, see the
    strategy PRD's payoff section for why: it mis-selects strike moneyness).
    """
    expiry_cache.refresh([symbol])
    conn = get_connection()
    try:
        inputs = prepare_run_inputs(conn, start_date, end_date, symbol, price_source)
        if inputs is None:
            return None
        window_starts = inputs["window_starts"]

        windows_out = []
        for i, ws in enumerate(window_starts):
            window_end_ts = ist_ts_for(window_starts[i + 1], ENTRY_TIME) if i + 1 < len(window_starts) else None
            embed = compute_window_embed(conn, ws, window_end_ts, inputs["merged"], up_move, leg_gap,
                                          inputs["fut_series"], symbol, inputs["lot_size"], strike_multiple,
                                          initial_gap, side)
            if embed is not None:
                windows_out.append(embed)

        if not windows_out:
            return None

        return {
            "windows": windows_out, "up_move": up_move, "leg_gap": leg_gap,
            "price_source": price_source, "fut_trading_symbol": inputs["price_label"],
            "lot_size": inputs["lot_size"], "start_date": start_date, "end_date": inputs["end_date"],
        }
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start-date", required=True)
    ap.add_argument("--end-date", default=None, help="default: latest date with local option_chain_5m data")
    ap.add_argument("--up-move", type=float, default=100)
    ap.add_argument("--leg-gap", type=float, default=400)
    ap.add_argument("--strike-multiple", type=float, default=100,
                     help="K-strike rounding step (floor for PE, ceil for CE) — defaults to 100, NIFTY's real strike spacing")
    ap.add_argument("--initial-gap", type=float, default=0,
                     help="shift K before rounding — positive pushes further OTM, negative toward/into ITM "
                          "(sign auto-flips PE vs CE, same convention as leg_gap)")
    ap.add_argument("--side", choices=["PE", "CE", "BOTH"], default="BOTH",
                     help="which side(s) to actually compute — a side not selected is skipped entirely, not just hidden")
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--price-source", choices=["fut", "spot"], default="fut",
                     help="fut (default): live front-month NIFTY future via Upstox. spot: local candles_5m "
                          "NIFTY50 index closes, no live Upstox call for the price series — see "
                          "nifty_pe_ratio_diagonal_windowed_backtest.py for the same flag's rationale.")
    ap.add_argument("--output", required=True, help="path to write the publishable HTML file")
    args = ap.parse_args()

    result = run_merged_windows_backtest(args.start_date, args.end_date, args.up_move, args.leg_gap,
                                          args.symbol, args.price_source, args.strike_multiple,
                                          args.initial_gap, args.side)
    if result is None:
        print("No usable windows (or no local data yet) — aborting, nothing written.")
        sys.exit(1)

    print(f"Windows in [{result['start_date']}, {result['end_date']}]: "
          f"{[w['entry_date'] for w in result['windows']]}")
    for embed in result["windows"]:
        pe_tag = f"PE {embed['pe_realized_pnl_pts']:+.2f}" if embed["pe_ok"] else "PE FAILED"
        ce_tag = f"CE {embed['ce_realized_pnl_pts']:+.2f}" if embed["ce_ok"] else "CE FAILED"
        print(f"  Window {embed['entry_date']}: {len(embed['sets'])} set(s) total — {pe_tag} pts, {ce_tag} pts")

    template = open(TEMPLATE_PATH, encoding="utf-8").read()
    data_json = json.dumps({k: v for k, v in result.items() if k not in ("start_date", "end_date")},
                            separators=(",", ":"))
    final_html = template.replace("__DATA_PLACEHOLDER__", data_json)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(final_html)
    print(f"\nWrote {len(final_html)} bytes to {args.output}")


if __name__ == "__main__":
    main()
