"""
NIFTY PE ratio diagonal — windowed-backtest artifact builder.

Consolidates what was, up through 2026-09-09, a manual multi-step process
(run the windowed backtest, hand-write a python snippet to merge in futures
prices and split realized/reference daily rollups, hand-substitute into the
HTML template, publish) into one script + one committed template
(`nifty_pe_ratio_diagonal_windows_template.html`, same directory).

Reuses nifty_pe_ratio_diagonal_windowed_backtest.py's own functions
(find_window_starts, run_window) directly — this is not a re-implementation,
just the missing "turn that into a publishable artifact" step.

Per window, builds:
  - combined: every tick (fut, pnl_pts, pnl_rs, active_sets, post_exit flag)
  - daily_realized: EOD rollup of pre-exit ticks only (what was actually realized)
  - daily_reference: EOD rollup of ALL ticks (the "if held to actual
    settlement instead" comparison) — only present when the window is
    bounded (a later window exists); the newest/still-open window has none.

Usage:
    cd backend && source venv/bin/activate
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_windows_artifact.py \
        --start-date 2026-08-25 --output /tmp/windows_artifact.html

Then publish /tmp/windows_artifact.html with the Artifact tool, passing
`url` = the existing rolling-windows artifact URL to update it in place
(see docs/prd/pe-ratio-diagonal-strategy.md for that URL) rather than
create a new one.
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.queries import get_merged_cadence_dates
from db.init_db import get_connection
from live.expiry import expiry_cache
from nifty_pe_ratio_diagonal_windowed_backtest import find_window_starts, run_window, ist_ts_for, ENTRY_TIME
from nifty_fut_ref import resolve_front_month_future, fetch_candles_utc

SYMBOL = "NIFTY50"
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "nifty_pe_ratio_diagonal_windows_template.html")


def rollup_daily(points: list[dict]) -> list[dict]:
    """EOD (last-tick-per-day) rollup: day, close_pnl_pts, close_pnl_rs."""
    days = sorted({p["day"] for p in points})
    out = []
    for d in days:
        day_points = [p for p in points if p["day"] == d]
        out.append({
            "day": d, "close_pnl_pts": day_points[-1]["pnl_pts"], "close_pnl_rs": day_points[-1]["pnl_rs"],
            "active_sets": day_points[-1]["active_sets"],
        })
    return out


def build_window_embed(win: dict, fut_series: dict, lot_size: int) -> dict:
    """Reshape one run_window() result into the artifact's per-window JSON shape."""
    combined = []
    for p in win["combined_points"]:
        f = fut_series.get(p["ts"])
        if f is None:
            continue
        combined.append({
            "ts": p["ts"], "day": p["ts"][:10], "fut": f,
            "pnl_pts": p["pnl_pts"], "pnl_rs": round(p["pnl_pts"] * lot_size, 2),
            "active_sets": win["n_sets"], "post_exit": p["post_exit"],
        })

    pre_exit = [p for p in combined if not p["post_exit"]]
    daily_realized = rollup_daily(pre_exit)
    daily_reference = rollup_daily(combined) if win["is_bounded"] else []

    # Only sets that actually priced (have entry_value/k_strike etc.) belong
    # in the embed — a pure error/skip entry (wrong-window triplet mismatch,
    # no tradeable strike found) has neither, and the template's set-card
    # renderer does `s.k_strike.toFixed(0)` unconditionally: one such entry
    # throws and silently aborts the whole page's init(), so NOTHING renders
    # (confirmed 2026-09-09 — this is why a window with a skipped trigger
    # showed a completely blank artifact instead of just missing that card).
    sets_out = [{k: v for k, v in s.items() if k != "values"} for s in win["sets"] if "entry_value" in s]
    return {
        "entry_date": win["window_start"], "up_move": win.get("up_move"), "leg_gap": win.get("leg_gap"),
        "side": win.get("side"),
        "fut_trading_symbol": win.get("fut_trading_symbol"), "lot_size": lot_size,
        "is_bounded": win["is_bounded"], "exit_ts": win["exit_ts"],
        "realized_pnl_pts": win["realized_pnl_pts"], "realized_pnl_rs": round(win["realized_pnl_pts"] * lot_size, 2),
        "latest_pnl_pts": win["latest_pnl_pts"], "latest_pnl_rs": round(win["latest_pnl_pts"] * lot_size, 2),
        "sets": sets_out, "combined": combined,
        "daily_realized": daily_realized, "daily_reference": daily_reference,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start-date", required=True)
    ap.add_argument("--end-date", default=None, help="default: latest date with local option_chain_5m data")
    ap.add_argument("--up-move", type=float, default=100)
    ap.add_argument("--leg-gap", type=float, default=400)
    ap.add_argument("--side", choices=["PE", "CE"], default="PE")
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--output", required=True, help="path to write the publishable HTML file")
    args = ap.parse_args()

    expiry_cache.refresh([args.symbol])
    conn = get_connection()

    if args.end_date is None:
        cur = conn.execute("SELECT MAX(ts) FROM option_chain_5m")
        max_ts = cur.fetchone()[0]
        if not max_ts:
            print("No data in option_chain_5m — aborting.")
            sys.exit(1)
        args.end_date = max_ts[:10]

    merged = get_merged_cadence_dates(args.symbol, include_quarterly=True)
    if len(merged) < 3:
        print(f"Not enough expiry history: {merged}")
        sys.exit(1)

    window_starts = find_window_starts(args.start_date, args.end_date, merged)
    if not window_starts:
        print(f"No trading days in [{args.start_date}, {args.end_date}].")
        sys.exit(1)

    fut = resolve_front_month_future("NIFTY")
    lot_size = fut["lot_size"]
    pad_from = (date.fromisoformat(args.start_date) - timedelta(days=1)).isoformat()
    pad_to = (date.fromisoformat(args.end_date) + timedelta(days=1)).isoformat()
    fut_series = fetch_candles_utc(fut["instrument_key"], pad_from, pad_to)
    if not fut_series:
        print(f"No futures history for {fut['trading_symbol']} — aborting.")
        sys.exit(1)

    print(f"Windows in [{args.start_date}, {args.end_date}]: {window_starts}")

    windows_out = []
    for i, ws in enumerate(window_starts):
        window_end_ts = ist_ts_for(window_starts[i + 1], ENTRY_TIME) if i + 1 < len(window_starts) else None
        res = run_window(conn, ws, window_end_ts, merged, args.up_move, args.leg_gap, fut_series, args.symbol,
                          side=args.side)
        if "combined_points" not in res:
            print(f"  Window {ws}: FAILED — {res.get('error')} — skipped from artifact")
            continue
        res["up_move"], res["leg_gap"], res["fut_trading_symbol"] = args.up_move, args.leg_gap, fut["trading_symbol"]
        res["side"] = args.side
        embed = build_window_embed(res, fut_series, lot_size)
        windows_out.append(embed)
        tag = f"realized {embed['realized_pnl_pts']:+.2f}" if embed["is_bounded"] else f"open, latest {embed['latest_pnl_pts']:+.2f}"
        print(f"  Window {ws}: {len(embed['sets'])} set(s), {tag} pts")
    conn.close()

    if not windows_out:
        print("No usable windows — aborting, nothing written.")
        sys.exit(1)

    template = open(TEMPLATE_PATH, encoding="utf-8").read()
    data_json = json.dumps({"windows": windows_out}, separators=(",", ":"))
    final_html = template.replace("__DATA_PLACEHOLDER__", data_json)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(final_html)
    print(f"\nWrote {len(final_html)} bytes to {args.output}")
    print("Publish with the Artifact tool, passing `url` = the existing rolling-windows artifact URL "
          "(see docs/prd/pe-ratio-diagonal-strategy.md) to update it in place.")


if __name__ == "__main__":
    main()
