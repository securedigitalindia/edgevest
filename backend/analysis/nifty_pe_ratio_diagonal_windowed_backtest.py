"""
NIFTY PE ratio diagonal — windowed backtest: chains the averaging-entry
backtest (nifty_pe_ratio_diagonal_averaging_backtest.py) across every
natural expiry-triplet window in a date range, instead of the caller
picking each window's start date by hand.

A new window begins on the first trading day whose OWN resolve_expiry_triplet
resolves a DIFFERENT expiry1 than the current window's — i.e. exactly when
the natural DTE>1 rollover happens (the same rollover that already governed
every manually-run window this project has tested: Aug25 uses expiry1=Sep1
through Aug28, Aug31 flips to expiry1=Sep8, Sep7 flips to expiry1=Sep15).
Within each window, the same +100-pt-up-move averaging trigger applies
(build_set, reused unchanged from the averaging script) — but a window's
own trigger-scanning AND its own combined-P&L tracking are both bounded to
stop before the NEXT window's start, so adjacent windows can never overlap
in time. 2026-09-09: this used to let a window run all the way to its own
expiry1's actual settlement (3:30pm on expiry day) — which can land well
after the next window has already begun (e.g. Aug25's expiry1 settles
Sep1, a full day after the Aug31 window started) — so exit is now planned
for the moment the next window's entry happens, matching a rolling weekly
strategy that closes out and re-enters at each rollover rather than
holding two overlapping windows. The newest, still-open window (no next
window yet) is unbounded — tracks through the latest available data.

Usage:
    cd backend && source venv/bin/activate
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_windowed_backtest.py \
        --start-date 2026-08-25
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_windowed_backtest.py \
        --start-date 2026-08-25 --end-date 2026-09-08 --up-move 100 \
        --export-json /tmp/windowed.json
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from live.holidays import is_trading_day
from live.expiry import expiry_cache
from db.queries import get_merged_cadence_dates
from db.init_db import get_connection
from nifty_pe_ratio_diagonal_simulator import resolve_expiry_triplet, floor_strike_100
from nifty_pe_ratio_diagonal_averaging_backtest import build_set, SIDE_CONFIG
from nifty_fut_ref import resolve_front_month_future, fetch_candles_utc, IST

SYMBOL = "NIFTY50"
ENTRY_TIME = time(9, 30)


def ist_ts_for(day: str, t: time) -> str:
    dt_ist = datetime.combine(date.fromisoformat(day), t, tzinfo=IST)
    return dt_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_window_starts(start_date: str, end_date: str, merged: list[str]) -> list[str]:
    """Every date a new expiry1-triplet window begins, in [start_date, end_date]."""
    starts = []
    current_e1 = None
    d, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    while d <= end:
        if is_trading_day(d):
            try:
                e1, _, _ = resolve_expiry_triplet(d.isoformat(), merged)
            except ValueError:
                break  # ran out of known future expiries — stop, don't guess
            if e1 != current_e1:
                starts.append(d.isoformat())
                current_e1 = e1
        d += timedelta(days=1)
    return starts


def run_window(conn, window_start: str, window_end_ts: str | None, merged: list[str],
                up_move: float, leg_gap: float, fut_series: dict, symbol: str,
                side: str = "PE", strike_multiple: float = 100, initial_gap: float = 0) -> dict:
    trigger_dir = SIDE_CONFIG[side]["trigger_dir"]
    entry_target_ts = ist_ts_for(window_start, ENTRY_TIME)
    all_ts = sorted(
        t for t in fut_series
        if t >= entry_target_ts and (window_end_ts is None or t < window_end_ts)
        and is_trading_day(date.fromisoformat(t[:10]))
    )
    if not all_ts:
        return {"window_start": window_start, "error": "no futures ticks in this window's trigger-scan range"}

    trigger_points = [(all_ts[0], fut_series[all_ts[0]])]
    last_trigger_fut = fut_series[all_ts[0]]
    for ts in all_ts[1:]:
        f = fut_series[ts]
        if (f - last_trigger_fut) * trigger_dir >= up_move:
            trigger_points.append((ts, f))
            last_trigger_fut = f

    # A window IS one expiry-triplet — that's literally how its own start
    # was detected (find_window_starts). An averaging trigger that fires
    # late enough in the window that ITS OWN date's fresh resolution has
    # already rolled over to the NEXT triplet is not this window's trade —
    # it's shaped exactly like the next window's own entry, just fired a
    # day early through this window's averaging scan. Lock every set in
    # this window to the window's own triplet, and skip (don't create) any
    # trigger whose own date no longer resolves to it — that move is picked
    # up by the next window's own fresh entry instead, not duplicated here.
    try:
        window_triplet = resolve_expiry_triplet(window_start, merged)
    except ValueError as e:
        return {"window_start": window_start, "error": f"could not resolve this window's own triplet: {e}"}

    sets = []
    for ts, f in trigger_points:
        try:
            trigger_triplet = resolve_expiry_triplet(ts[:10], merged)
        except ValueError as e:
            sets.append({"trigger_ts": ts, "trigger_fut": f, "error": str(e)})
            continue
        if trigger_triplet != window_triplet:
            sets.append({
                "trigger_ts": ts, "trigger_fut": f,
                "error": f"trigger's own expiry-triplet {trigger_triplet} differs from this window's "
                         f"{window_triplet} — belongs to the next window, skipped here",
            })
            continue
        sets.append(build_set(conn, ts, f, merged, leg_gap, symbol, side=side, expiry_triplet=window_triplet,
                               strike_multiple=strike_multiple, initial_gap=initial_gap))

    # A set's real entry (build_set's trigger_ts, now delayed to the first
    # tick where every leg has genuine price discovery — see chain_series's
    # zero-LTP fix) can land AFTER this window's own exit boundary: the far
    # leg simply hadn't traded yet by the time the window rolled over. That
    # set never had a chance to be an active position before this window
    # closed, so it's dropped from this window's P&L entirely rather than
    # silently contributing zero — flagged, not counted, not guessed at.
    for s in sets:
        if "values" in s and window_end_ts is not None and s["trigger_ts"] >= window_end_ts:
            s["never_filled_before_rollover"] = True

    ok_sets = [s for s in sets if "values" in s and not s.get("never_filled_before_rollover")]
    if not ok_sets:
        return {"window_start": window_start, "sets": sets, "error": "no usable sets in this window"}

    # The "if held to actual settlement" reference must stop at the WINDOW's
    # own expiry1 settlement (3:30pm IST on expiry day) — not whenever the
    # union of every triggered set's own data happens to run out. A later
    # averaging-triggered set gets its OWN fresh (later) expiry triplet, so
    # its near-leg data keeps going well past the window's own expiry1 —
    # on the CE side, which fires more/later sets than PE, this silently
    # stretched the reference series all the way to "today" instead of
    # stopping at the window's own settlement point. Cap it explicitly.
    expiry1_settle_ts = ist_ts_for(ok_sets[0]["expiry1"], time(15, 30))

    # Exit is planned for the moment the NEXT window's entry happens (a
    # rolling weekly strategy closes out and re-enters at the rollover,
    # rather than holding two overlapping windows — the Aug25 window's
    # expiry1 settles Sep1, a full day after the Aug31 window already
    # began, if left to run to actual settlement). But the data beyond
    # that exit point is real and worth keeping visible for comparison —
    # "what would this window have been worth had it been held to its own
    # near leg's actual settlement instead" — so the full natural range is
    # kept here, just tagged with post_exit so callers can distinguish
    # realized P&L (pre-exit) from the hypothetical hold-to-settlement
    # continuation (post-exit).
    # Only cap for a BOUNDED window (one that has actually exited) — an
    # unbounded/still-open window has no "if held" hypothetical to bound;
    # it's genuinely live tracking and should keep extending through the
    # latest available data, same as before.
    all_union_ts = set().union(*[s["values"].keys() for s in ok_sets])
    if window_end_ts is not None:
        all_union_ts = {t for t in all_union_ts if t <= expiry1_settle_ts}
    combined_ts = sorted(all_union_ts)
    last_pnl_cache = {id(s): 0.0 for s in ok_sets}
    combined_points = []
    for ts in combined_ts:
        total = 0.0
        for s in ok_sets:
            if ts < s["trigger_ts"]:
                continue
            if ts in s["values"]:
                last_pnl_cache[id(s)] = round(s["values"][ts] - s["entry_value"], 2)
            total += last_pnl_cache[id(s)]
        combined_points.append({
            "ts": ts, "pnl_pts": round(total, 2),
            "post_exit": window_end_ts is not None and ts >= window_end_ts,
        })

    pre_exit = [p for p in combined_points if not p["post_exit"]]
    if not pre_exit:
        return {"window_start": window_start, "sets": sets, "error": "no ticks before this window's exit boundary"}
    exit_ts = pre_exit[-1]["ts"]
    realized_pnl_pts = pre_exit[-1]["pnl_pts"]

    # Each set's own exit_ts/n_ticks_at_exit reflect this WINDOW's exit
    # boundary (when the position was actually closed); last_ts/n_ticks (from
    # build_set) are left as the full natural range — both are kept since
    # both are now meaningful (realized vs. hold-to-settlement).
    for s in ok_sets:
        at_exit = [ts for ts in combined_ts if s["trigger_ts"] <= ts <= exit_ts]
        s["exit_ts"] = at_exit[-1] if at_exit else s["trigger_ts"]
        s["n_ticks_at_exit"] = len(at_exit)

    # current_value / exit_value (2026-09-09): two different reference
    # points on the same combo, both computed here before "values" (the
    # full tick series) is stripped below.
    #   - current_value: value at this set's own last_ts — the full natural
    #     range, not capped to the window's exit boundary. For an unbounded
    #     (still-open) window this IS the live/latest figure; for a bounded
    #     window it's the "if held past exit" reference, same spirit as
    #     latest_pnl_pts/daily_reference elsewhere in this window.
    #   - exit_value: value at this set's own exit_ts (set just above,
    #     capped to the WINDOW's real exit boundary) — the actually-realized
    #     figure once a window has settled. Only meaningful when the window
    #     is bounded; for an unbounded window exit_ts and last_ts coincide
    #     (post_exit never fires), so exit_value == current_value there —
    #     harmless, not a special case that needs its own branch.
    # A set without "values" (a resolution error, or dropped for never
    # filling before rollover) has no exit_ts either, so both come out None.
    def _with_reference_values(s):
        out = {k: v for k, v in s.items() if k != "values"}
        vals = s.get("values") or {}
        out["current_value"] = vals.get(s.get("last_ts"))
        out["exit_value"] = vals.get(s.get("exit_ts"))
        return out

    return {
        "window_start": window_start,
        "expiry1": ok_sets[0]["expiry1"],
        "sets": [_with_reference_values(s) for s in sets],
        "n_sets": len(ok_sets),
        "entry_ts": combined_points[0]["ts"],
        "exit_ts": exit_ts,
        "realized_pnl_pts": realized_pnl_pts,
        "is_bounded": window_end_ts is not None,
        "latest_ts": combined_points[-1]["ts"],
        "latest_pnl_pts": combined_points[-1]["pnl_pts"],
        "n_ticks": len(combined_points),
        "combined_points": combined_points,
    }


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
    ap.add_argument("--side", choices=["PE", "CE"], default="PE")
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--price-source", choices=["fut", "spot"], default="fut",
                     help="fut (default): live front-month NIFTY future via Upstox, as used in every prior run. "
                          "spot: local candles_5m NIFTY50 index closes, no live Upstox call for the price series "
                          "— an experiment to see how much the strike-selection/trigger basis matters, per the "
                          "strategy PRD's basis-gap note (index vs future diverged ~150pts on 2026-09-07).")
    ap.add_argument("--export-json", default=None)
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

    pad_from = (date.fromisoformat(args.start_date) - timedelta(days=1)).isoformat()
    pad_to = (date.fromisoformat(args.end_date) + timedelta(days=1)).isoformat()

    if args.price_source == "fut":
        fut = resolve_front_month_future("NIFTY")
        lot_size = fut["lot_size"]
        price_label = fut["trading_symbol"]
        fut_series = fetch_candles_utc(fut["instrument_key"], pad_from, pad_to)
    else:
        # NIFTY50 index closes from local candles_5m — no live Upstox call.
        # candles_5m stores ts as 'YYYY-MM-DD HH:MM:SS+00:00'; normalize to
        # the 'YYYY-MM-DDTHH:MM:SSZ' shape every other ts in this pipeline uses.
        lot_size = 65  # last-known NIFTY lot size (nifty_fut_ref.py) — no live resolution in spot mode
        price_label = f"{args.symbol} SPOT"
        rows = conn.execute(
            "SELECT ts, close FROM candles_5m WHERE symbol = ? AND ts >= ? AND ts < ? ORDER BY ts",
            (args.symbol, pad_from, pad_to),
        ).fetchall()
        fut_series = {
            datetime.fromisoformat(ts).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"): close
            for ts, close in rows
        }

    if not fut_series:
        print(f"No {args.price_source} price history for {args.symbol} — aborting.")
        sys.exit(1)

    print(f"Windows in [{args.start_date}, {args.end_date}]: {window_starts}\n")

    results = []
    for i, ws in enumerate(window_starts):
        window_end_ts = ist_ts_for(window_starts[i + 1], ENTRY_TIME) if i + 1 < len(window_starts) else None
        res = run_window(conn, ws, window_end_ts, merged, args.up_move, args.leg_gap, fut_series, args.symbol,
                          side=args.side, strike_multiple=args.strike_multiple, initial_gap=args.initial_gap)
        results.append(res)
        if "combined_points" not in res:
            print(f"Window {ws}: FAILED — {res.get('error')}")
            continue
        print(f"Window {ws}  (expiry1={res['expiry1']}, {res['n_sets']} set(s)):")
        for s in res["sets"]:
            if "entry_value" not in s:
                continue
            tag = "  [DROPPED — never filled before this window's rollover]" if s.get("never_filled_before_rollover") else ""
            if s.get("strike_overrides"):
                tag += f"  [strike fallback used: {s['strike_overrides']}]"
            print(f"    SET @ {s['trigger_ts']}  fut={s['trigger_fut']:.1f}: "
                  f"K={s['k_strike']:.0f}/{s['k2_strike']:.0f}  "
                  f"expiries={s['expiry1']}/{s['expiry2']}/{s['expiry3']}  entry={s['entry_value']:.2f}{tag}")
        if res["is_bounded"]:
            print(f"    REALIZED (exit at next window's entry): {res['exit_ts']}  "
                  f"pnl_pts={res['realized_pnl_pts']:+.2f}  pnl_rs={res['realized_pnl_pts'] * lot_size:+.2f}")
            print(f"    if held to actual settlement instead: {res['latest_ts']}  "
                  f"pnl_pts={res['latest_pnl_pts']:+.2f}  pnl_rs={res['latest_pnl_pts'] * lot_size:+.2f}\n")
        else:
            print(f"    combined (still open, unbounded): entry {res['entry_ts']} -> latest {res['latest_ts']}  "
                  f"pnl_pts={res['latest_pnl_pts']:+.2f}  pnl_rs={res['latest_pnl_pts'] * lot_size:+.2f}  "
                  f"({res['n_ticks']} ticks)\n")
    conn.close()

    ok = [r for r in results if "combined_points" in r]
    print(f"{len(ok)}/{len(results)} window(s) produced a usable result.")
    if ok:
        total_realized = sum((r["realized_pnl_pts"] if r["is_bounded"] else r["latest_pnl_pts"]) for r in ok)
        print(f"Sum of every window's own REALIZED pnl_pts (exit at next window's entry; NOT a single "
              f"continuous position — each window is independent): {total_realized:+.2f} pts, "
              f"{total_realized * lot_size:+.2f} rs across {len(ok)} window(s).")

    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump({
                "start_date": args.start_date, "end_date": args.end_date,
                "up_move": args.up_move, "leg_gap": args.leg_gap, "side": args.side,
                "price_source": args.price_source, "fut_trading_symbol": price_label, "lot_size": lot_size,
                "windows": results,
            }, f, indent=2)
        print(f"Exported to {args.export_json}")


if __name__ == "__main__":
    main()
