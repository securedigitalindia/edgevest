"""
NIFTY PE+CE 1:2 calendar ratio spread — weekly-window backtest.

Per side (PE and CE, independent — same convention as the PE+CE ratio
diagonal), one 2-leg CALENDAR ratio position:
    BUY  1x K            on the UPCOMING expiry   (K = base strike next to the futures price)
    SELL 2x K2 = K ± leg_gap  on the NEXT expiry after that
K is chosen like the diagonal's: PE floors / CE ceils (fut + signed
initial_gap) to strike_multiple, so initial_gap=0 is the nearest OTM strike
and a positive initial_gap pushes K further OTM. leg_gap defaults to 0 — a
pure calendar (same strike, two expiries); a non-zero leg_gap shifts only
the 2x far leg's strike (further OTM), making it a diagonal.

Expiries: the "upcoming" one is the nearest with DTE > 2 at entry — so an
entry on Monday skips the next-day (Tuesday) expiry and uses the following
week's; far = the expiry right after it.

Schedule (one independent window per week):
    entry : 09:30 IST on the selected weekday (entry_weekday) — fut price at
            the first tick at/after 09:30 picks K.
    exit  : 15:00 IST on the first Monday strictly after the entry date (the
            previous trading day if that Monday is a holiday; never later
            than the upcoming expiry's own date).
After the exit the window keeps its data up to the upcoming expiry's 15:30
settlement as a tagged "if held to settlement" reference, same as the
diagonal's windows.

Output windows reuse build_merged_embed()'s shape unchanged so the admin
dashboard's tiles/charts/tables render them as-is.

Usage:
    cd backend && source venv/bin/activate
    FLASK_ENV=dev python analysis/nifty_ratio_spread_1x2_backtest.py \
        --start-date 2026-08-24 --entry-weekday WED
"""
import argparse
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from live.holidays import is_trading_day
from live.expiry import expiry_cache
from db.queries import get_merged_cadence_dates
from db.init_db import get_connection
from nifty_pe_ratio_diagonal_averaging_backtest import SIDE_CONFIG, _priced_leg
from nifty_pe_ratio_diagonal_backtest import ist_ts_for
from nifty_pe_ratio_diagonal_merged_windows_artifact import build_merged_embed
from nifty_fut_ref import resolve_front_month_future, fetch_candles_utc, fetch_intraday_candles_utc, IST

SYMBOL = "NIFTY50"
ENTRY_TIME = time(9, 30)
EXIT_TIME = time(15, 0)
SETTLE_TIME = time(15, 30)
WEEKDAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4}


def resolve_near_far(entry: date, merged: list[str]) -> tuple[str, str] | None:
    """(upcoming, next-after-upcoming) expiry — upcoming = nearest with DTE > 2 (skips a Monday entry's Tuesday expiry)."""
    upcoming = [e for e in merged if (date.fromisoformat(e) - entry).days > 2]
    return (upcoming[0], upcoming[1]) if len(upcoming) >= 2 else None


def exit_date_for(entry: date, near_expiry: str) -> date | None:
    """First Monday strictly after `entry`, rolled back to the previous trading day if it's a holiday, and never
    later than the upcoming expiry's own date (a holiday-shifted expiry can land before that Monday)."""
    d = entry + timedelta(days=(7 - entry.weekday()) % 7 or 7)
    d = min(d, date.fromisoformat(near_expiry))
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d if d > entry else None


def find_entry_dates(start_date: str, end_date: str, weekday: str) -> list[str]:
    target = WEEKDAYS[weekday]
    d, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    out = []
    while d <= end:
        if d.weekday() == target and is_trading_day(d):
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def build_ratio_set(conn, entry_ts: str, fut_price: float, near: str, far: str, leg_gap: float, symbol: str,
                    side: str, strike_multiple: float, initial_gap: float) -> dict:
    cfg = SIDE_CONFIG[side]
    k = cfg["strike_fn"](fut_price + cfg["gap_sign"] * initial_gap, strike_multiple)
    k2 = k + cfg["gap_sign"] * leg_gap
    (l1, l1_strike), (l2, l2_strike) = (
        _priced_leg(conn, near, k, cfg["opt_type"], symbol, entry_ts),
        _priced_leg(conn, far, k2, cfg["opt_type"], symbol, entry_ts),
    )
    meta = {"trigger_ts": entry_ts, "trigger_fut": fut_price, "side": side,
            "k_strike": k, "k2_strike": k2, "expiry1": near, "expiry2": far}
    if l1 is None or l2 is None:
        meta["error"] = "no tradeable strike (nominal or ±100) found for one or more legs from entry onward"
        return meta

    overrides = {leg: used for leg, used, nominal in (("l1", l1_strike, k), ("l2", l2_strike, k2)) if used != nominal}
    if overrides:
        meta["strike_overrides"] = overrides

    common_ts = [ts for ts in sorted(set(l1) & set(l2))
                 if ts >= entry_ts and is_trading_day(date.fromisoformat(ts[:10]))]
    if not common_ts:
        meta["error"] = "no local chain data for this position from its entry onward"
        return meta

    values = {ts: round(l1[ts] - 2 * l2[ts], 2) for ts in common_ts}
    first = common_ts[0]
    meta["entry_legs"] = {"l1": l1[first], "l2": l2[first]}
    meta["legs"] = {"l1": l1, "l2": l2}
    meta.update({"trigger_ts": first, "entry_value": values[first], "last_ts": common_ts[-1],
                 "values": values, "n_ticks": len(values)})
    return meta


def run_window_1x2(conn, entry_date: str, merged: list[str], leg_gap: float, fut_series: dict, symbol: str,
                   side: str, strike_multiple: float, initial_gap: float) -> dict:
    pair = resolve_near_far(date.fromisoformat(entry_date), merged)
    if pair is None:
        return {"window_start": entry_date, "error": "fewer than two known expiries with DTE > 2"}
    expiry, far = pair
    exit_d = exit_date_for(date.fromisoformat(entry_date), expiry)
    if exit_d is None:
        return {"window_start": entry_date, "error": "no valid exit Monday after this entry date"}

    entry_target = ist_ts_for(entry_date, ENTRY_TIME)
    entry_ticks = sorted(t for t in fut_series if t >= entry_target and t[:10] == entry_target[:10])
    if not entry_ticks:
        return {"window_start": entry_date, "error": "no futures tick at/after entry time on the entry date"}
    entry_ts, entry_fut = entry_ticks[0], fut_series[entry_ticks[0]]

    s = build_ratio_set(conn, entry_ts, entry_fut, expiry, far, leg_gap, symbol, side, strike_multiple, initial_gap)
    if "values" not in s:
        return {"window_start": entry_date, "sets": [s], "error": s.get("error", "unusable position")}

    settle_ts = ist_ts_for(expiry, SETTLE_TIME)
    exit_target = ist_ts_for(exit_d.isoformat(), EXIT_TIME)
    vals = {t: v for t, v in s["values"].items() if t <= settle_ts}
    if not vals:
        return {"window_start": entry_date, "sets": [s], "error": "no ticks on or before the expiry settlement"}
    points, is_bounded = [], any(t > exit_target for t in vals) or max(vals) >= exit_target
    for ts in sorted(vals):
        points.append({"ts": ts, "pnl_pts": round(vals[ts] - s["entry_value"], 2),
                       "post_exit": ts > exit_target})
    pre_exit = [p for p in points if not p["post_exit"]]
    if not pre_exit:
        return {"window_start": entry_date, "sets": [s], "error": "no ticks before this window's exit time"}
    exit_ts = pre_exit[-1]["ts"] if is_bounded else None

    def snap(legs, ts):
        try:
            return {k: series[ts] for k, series in legs.items()} if ts else None
        except KeyError:
            return None

    out_set = {k: v for k, v in s.items() if k not in ("values", "legs")}
    out_set["current_value"] = vals.get(points[-1]["ts"])
    out_set["exit_value"] = vals.get(exit_ts) if exit_ts else None
    out_set["last_ts"] = points[-1]["ts"]
    out_set["exit_ts"] = exit_ts
    out_set["exit_legs"] = snap(s["legs"], exit_ts)
    out_set["current_legs"] = snap(s["legs"], points[-1]["ts"])

    return {
        "window_start": entry_date, "expiry1": expiry, "expiry2": far, "sets": [out_set], "n_sets": 1,
        "entry_ts": points[0]["ts"], "exit_ts": exit_ts or points[-1]["ts"],
        "realized_pnl_pts": pre_exit[-1]["pnl_pts"] if is_bounded else points[-1]["pnl_pts"],
        "is_bounded": is_bounded, "latest_ts": points[-1]["ts"], "latest_pnl_pts": points[-1]["pnl_pts"],
        "n_ticks": len(points), "combined_points": points,
        "_exit_boundary": exit_target, "_expiry": expiry, "_far": far,
    }


def prepare_inputs(conn, start_date: str, end_date: str | None, symbol: str, weekday: str) -> dict | None:
    if weekday not in WEEKDAYS:
        raise ValueError(f"entry_weekday must be one of {sorted(WEEKDAYS)}")
    max_ts = conn.execute("SELECT MAX(ts) FROM option_chain_5m").fetchone()[0]
    if not max_ts:
        return None
    end_date = end_date or max_ts[:10]
    merged = get_merged_cadence_dates(symbol, include_quarterly=True)
    entry_dates = find_entry_dates(start_date, end_date, weekday)
    if not merged or not entry_dates:
        return None

    fut = resolve_front_month_future("NIFTY")
    pad_from = (date.fromisoformat(start_date) - timedelta(days=1)).isoformat()
    pad_to = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
    fut_series = fetch_candles_utc(fut["instrument_key"], pad_from, pad_to)
    # The historical endpoint never includes today's candles — see prepare_run_inputs() in the
    # merged-windows artifact for the chart/tile mismatch this avoids.
    if end_date >= datetime.now(timezone.utc).astimezone(IST).date().isoformat():
        fut_series.update(fetch_intraday_candles_utc(fut["instrument_key"]))
    if not fut_series:
        return None
    return {"end_date": end_date, "chain_max_ts": max_ts, "merged": merged, "entry_dates": entry_dates,
            "fut_series": fut_series, "lot_size": fut["lot_size"], "price_label": fut["trading_symbol"]}


def compute_window_embed_1x2(conn, entry_date: str, inputs: dict, params: dict, symbol: str) -> tuple[dict | None, bool]:
    """(embed | None, settled). settled = the local data has moved past this window's expiry date, so
    nothing about it can change again and it's safe to cache."""
    side = params.get("side", "BOTH")
    kw = dict(leg_gap=params.get("leg_gap", 0), fut_series=inputs["fut_series"], symbol=symbol,
              strike_multiple=params.get("strike_multiple", 100), initial_gap=params.get("initial_gap", 0))
    pe = run_window_1x2(conn, entry_date, inputs["merged"], side="PE", **kw) if side in ("PE", "BOTH") else {}
    ce = run_window_1x2(conn, entry_date, inputs["merged"], side="CE", **kw) if side in ("CE", "BOTH") else {}
    ok = [r for r in (pe, ce) if "combined_points" in r]
    if not ok:
        return None, False
    boundary = ok[0]["_exit_boundary"]
    bounded = any(r["is_bounded"] for r in ok)
    # build_merged_embed marks ts >= window_end_ts as post-exit; +1s makes that "strictly after the 15:00 tick".
    end_ts = (datetime.strptime(boundary, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ") \
        if bounded else None
    embed = build_merged_embed(pe, ce, entry_date, end_ts, inputs["fut_series"], inputs["lot_size"])
    embed["exit_ts"] = max((r["exit_ts"] for r in ok if r["is_bounded"]), default=None)
    embed["expiry"] = ok[0]["_expiry"]
    embed["expiry_far"] = ok[0]["_far"]
    settled = inputs["chain_max_ts"][:10] > ok[0]["_expiry"]
    return embed, settled


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start-date", required=True)
    ap.add_argument("--end-date", default=None)
    ap.add_argument("--entry-weekday", choices=sorted(WEEKDAYS), default="WED")
    ap.add_argument("--leg-gap", type=float, default=0, help="far-leg strike offset; 0 = same strike (pure calendar)")
    ap.add_argument("--strike-multiple", type=float, default=100)
    ap.add_argument("--initial-gap", type=float, default=0)
    ap.add_argument("--side", choices=["PE", "CE", "BOTH"], default="BOTH")
    ap.add_argument("--symbol", default=SYMBOL)
    args = ap.parse_args()

    expiry_cache.refresh([args.symbol])
    conn = get_connection()
    inputs = prepare_inputs(conn, args.start_date, args.end_date, args.symbol, args.entry_weekday)
    if inputs is None:
        print("No usable data for this range.")
        sys.exit(1)
    params = {"leg_gap": args.leg_gap, "strike_multiple": args.strike_multiple,
              "initial_gap": args.initial_gap, "side": args.side}
    lot = inputs["lot_size"]
    total = {"PE": 0.0, "CE": 0.0}
    for ed in inputs["entry_dates"]:
        embed, settled = compute_window_embed_1x2(conn, ed, inputs, params, args.symbol)
        if embed is None:
            print(f"{ed}: no usable result")
            continue
        for s in embed["sets"]:
            print(f"  {ed} {s['side']} K={s['k_strike']:.0f}/{s['k2_strike']:.0f} exp={s['expiry1']}/{s['expiry2']} "
                  f"entry={s['entry_value']:.2f} legs={s['entry_legs']}")
        total["PE"] += embed["pe_realized_pnl_pts"]
        total["CE"] += embed["ce_realized_pnl_pts"]
        print(f"{ed} -> exit {embed['exit_ts']}  PE {embed['pe_realized_pnl_pts']:+.2f}  "
              f"CE {embed['ce_realized_pnl_pts']:+.2f}  (if held: PE {embed['pe_ref_pnl_pts']:+.2f} / "
              f"CE {embed['ce_ref_pnl_pts']:+.2f})  {'settled' if settled else 'not settled yet'}")
    print(f"Sum realized pts: PE {total['PE']:+.2f}  CE {total['CE']:+.2f}  (lot {lot})")
    conn.close()


if __name__ == "__main__":
    main()
