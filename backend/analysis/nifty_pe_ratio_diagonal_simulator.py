"""
NIFTY PE ratio diagonal spread — spot-move simulator (v1).

Strategy shape (2026-09-08: replaced the original 2-leg/2-expiry shape —
see git history for that version):

    LEG 1  BUY  1x   expiry1   strike K        PE
    LEG 2  SELL 2x   expiry2   strike K-gap    PE
    LEG 3  SELL 1x   expiry2   strike K        PE
    LEG 4  BUY  2x   expiry3   strike K-gap    PE

    (gap default 400, e.g. K=24000 -> K-gap=23600)

Legs 1+2 are the original diagonal (buy near/sell far at a -gap strike
step); legs 3+4 add its mirror one cycle further out — a same-strike-K
reverse calendar (buy expiry1 / sell expiry2) plus a same-strike (K-gap)
long calendar 2x (sell expiry2 / buy expiry3).

expiry1/2/3 are resolved by merging Upstox's weekly+monthly expiry buckets,
sorting real dates, and picking the first three with DTE > 1 relative to
the reference day (see `resolve_expiry_triplet` below) — never trust the
bucket alone (a monthly-coinciding date gets pulled out of the weekly
bucket even though it's 7 days after the prior weekly). See the
calendar-spread-debit-proxy skill for why. DTE > 1 (not just DTE != 0) is
required for expiry1 specifically because live execution is at 09:30 on
entry day — a leg with 1 DTE or less is already too close to be the
"near" leg of this construction.

K itself is **not** user-supplied: live execution snaps the front-month
NIFTY future's price down to the next-lower 100-multiple (`floor_strike_100`
— e.g. fut=24065 -> K=24000). `--k-strike` can override this for manual
what-if runs.

v1 freezes time at "now" (no expiry rollforward, no DTE decay) and asks:
if the NIFTY future were at fut+move instead of fut, what would this
position be worth? Every leg's premium at fut+move is estimated by
looking up *today's actual live premium* at a strike shifted by -move
(the strike that has the same moneyness at today's real future price as
the original strike would have at the simulated level) — same strike-shift
proxy technique as the calendar-spread tool, just pulled live from Upstox
instead of the (currently stale) option_chain_5m table, since that table
doesn't have today's chain captured yet.

Reference price is the front-month NIFTY FUTURE's live LTP, not the index
spot the option-chain response bundles in (underlying_spot_price) — see
nifty_fut_ref.py's docstring for why they diverge and why that matters
for strike selection here.

This is a snapshot-in-time estimate, not a priced model: no time decay,
no IV-surface change, no interpolation between strikes (50pt grid only).

Usage:
    cd backend && source venv/bin/activate
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_simulator.py
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_simulator.py \
        --k-strike 24000 --leg-gap 400 --move-range 400 --move-step 100 \
        --export-json /tmp/pe_ratio_sim.json
"""
import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from live.expiry import expiry_cache
from live.option_chain_capture import capture_symbol
from nifty_fut_ref import resolve_front_month_future, get_live_fut_ltp, resolve_reference_trading_day, IST

SYMBOL = "NIFTY50"
STRIKE_GRID = 50


def fetch_live_chain(symbol: str = SYMBOL):
    """One live Upstox pull: full option chain, all captured expiries."""
    expiry_cache.refresh([symbol])
    rows = capture_symbol(symbol)
    if not rows:
        raise RuntimeError(
            f"No live option chain rows returned for {symbol} — check "
            f"UPSTOX_ACCESS_TOKEN validity and that the market/expiry data is available."
        )
    return rows


def merged_expiry_dates(rows: list[dict]) -> list[str]:
    """Distinct expiry_date values across every bucket Upstox returned, sorted ascending."""
    return sorted({r["expiry_date"] for r in rows})


def build_ltp_lookup(rows: list[dict]) -> dict:
    return {(r["expiry_date"], r["strike"], r["opt_type"]): r["ltp"] for r in rows}


def snap_strike(strike: float) -> float:
    return round(strike / STRIKE_GRID) * STRIKE_GRID


def floor_strike_100(price: float, multiple: float = 100) -> float:
    """Next-lower `multiple`-multiple — e.g. fut=24065, multiple=100 -> 24000. Used for live K
    selection (PE side: keeps the bought K-leg OTM, since a put is OTM when strike < spot).
    `multiple` defaults to 100 (NIFTY's real strike spacing) but is a real, user-facing config
    knob on the admin strategy dashboard (backend/strategies/registry.py) — kept as a parameter
    here rather than a hardcoded constant so that override actually reaches this function."""
    return math.floor(price / multiple) * multiple


def ceil_strike_100(price: float, multiple: float = 100) -> float:
    """Next-higher `multiple`-multiple — e.g. fut=24065, multiple=100 -> 24100. CE-side mirror of
    floor_strike_100: keeps the bought K-leg OTM, since a call is OTM when strike > spot."""
    return math.ceil(price / multiple) * multiple


def resolve_expiry_triplet(as_of_date: str, merged_expiries: list[str]) -> tuple[str, str, str]:
    """
    expiry1 = nearest expiry with DTE > 1 relative to as_of_date; expiry2/3 =
    the next two after that. DTE > 1 (not just != 0) because this strategy's
    live execution is at 09:30 on entry day — an expiry with 1 day left is
    already too close to entry to serve as the near leg.
    """
    d = date.fromisoformat(as_of_date)
    upcoming = [e for e in merged_expiries if (date.fromisoformat(e) - d).days > 1]
    if len(upcoming) < 3:
        raise ValueError(f"Not enough future expiries (DTE>1) for as_of={as_of_date}: {merged_expiries}")
    return upcoming[0], upcoming[1], upcoming[2]


def simulate_strategy(k_strike, leg_gap, expiry1, expiry2, expiry3,
                       lookup, fut, move_range, move_step, lot_size):
    """
    4-leg diagonal:
        Leg1  BUY  1x  K        PE  expiry1
        Leg2  SELL 2x  K-gap    PE  expiry2
        Leg3  SELL 1x  K        PE  expiry2
        Leg4  BUY  2x  K-gap    PE  expiry3
    """
    k2_strike = k_strike - leg_gap

    def leg_ltp(expiry, strike, move):
        proxy_strike = snap_strike(strike - move)
        ltp = lookup.get((expiry, proxy_strike, "PE"))
        return ltp, proxy_strike

    entry_l1, _ = leg_ltp(expiry1, k_strike, 0)
    entry_l2, _ = leg_ltp(expiry2, k2_strike, 0)
    entry_l3, _ = leg_ltp(expiry2, k_strike, 0)
    entry_l4, _ = leg_ltp(expiry3, k2_strike, 0)
    if None in (entry_l1, entry_l2, entry_l3, entry_l4):
        return None

    entry_debit = entry_l1 - 2 * entry_l2 - entry_l3 + 2 * entry_l4

    rows = []
    for move in range(-move_range, move_range + 1, move_step):
        l1, l1p = leg_ltp(expiry1, k_strike, move)
        l2, l2p = leg_ltp(expiry2, k2_strike, move)
        l3, l3p = leg_ltp(expiry2, k_strike, move)
        l4, l4p = leg_ltp(expiry3, k2_strike, move)
        if None in (l1, l2, l3, l4):
            rows.append({"move": move, "scenario_fut": fut + move, "missing": True,
                         "leg1_proxy_strike": l1p, "leg2_proxy_strike": l2p,
                         "leg3_proxy_strike": l3p, "leg4_proxy_strike": l4p})
            continue
        value = l1 - 2 * l2 - l3 + 2 * l4
        pnl_pts = value - entry_debit
        rows.append({
            "move": move,
            "scenario_fut": fut + move,
            "leg1_proxy_strike": l1p, "leg1_ltp": l1,
            "leg2_proxy_strike": l2p, "leg2_ltp": l2,
            "leg3_proxy_strike": l3p, "leg3_ltp": l3,
            "leg4_proxy_strike": l4p, "leg4_ltp": l4,
            "position_value": round(value, 2),
            "pnl_pts": round(pnl_pts, 2),
            "pnl_rs": round(pnl_pts * lot_size, 2),
        })
    return {
        "k_strike": k_strike, "k2_strike": k2_strike,
        "expiry1": expiry1, "expiry2": expiry2, "expiry3": expiry3,
        "entry_leg1_ltp": entry_l1, "entry_leg2_ltp": entry_l2,
        "entry_leg3_ltp": entry_l3, "entry_leg4_ltp": entry_l4,
        "entry_debit": round(entry_debit, 2),
        "scenarios": rows,
    }


def print_strategy(name, result):
    print(f"\n=== {name}: BUY 1x {result['k_strike']:.0f}PE ({result['expiry1']}) "
          f"/ SELL 2x {result['k2_strike']:.0f}PE ({result['expiry2']}) "
          f"/ SELL 1x {result['k_strike']:.0f}PE ({result['expiry2']}) "
          f"/ BUY 2x {result['k2_strike']:.0f}PE ({result['expiry3']}) ===")
    print(f"Entry: leg1={result['entry_leg1_ltp']}  leg2={result['entry_leg2_ltp']}  "
          f"leg3={result['entry_leg3_ltp']}  leg4={result['entry_leg4_ltp']}  "
          f"net debit={result['entry_debit']}  "
          f"({'credit' if result['entry_debit'] < 0 else 'debit'} to open)")
    header = (f"{'move':>6} {'fut':>9} {'l1_ltp':>8} {'l2_ltp':>8} {'l3_ltp':>8} {'l4_ltp':>8} "
              f"{'value':>9} {'pnl_pts':>9} {'pnl_rs':>10}")
    print(header)
    for s in result["scenarios"]:
        if s.get("missing"):
            print(f"{s['move']:>+6} {s['scenario_fut']:>9.0f}  -- no data at proxy strikes --")
            continue
        print(f"{s['move']:>+6} {s['scenario_fut']:>9.0f} {s['leg1_ltp']:>8.2f} {s['leg2_ltp']:>8.2f} "
              f"{s['leg3_ltp']:>8.2f} {s['leg4_ltp']:>8.2f} {s['position_value']:>9.2f} "
              f"{s['pnl_pts']:>+9.2f} {s['pnl_rs']:>+10.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k-strike", type=float, default=None,
                     help="leg1/leg3 strike override — default: live fut price floored to nearest 100")
    ap.add_argument("--leg-gap", type=float, default=400,
                     help="k_strike - k2_strike (k2 = leg2 sell 2x expiry2 / leg4 buy 2x expiry3)")
    ap.add_argument("--move-range", type=int, default=400, help="+/- fut points to simulate")
    ap.add_argument("--move-step", type=int, default=100, help="fut simulation step size")
    ap.add_argument("--lot-size", type=int, default=None,
                     help="NIFTY lot size for rupee P&L — default: resolved live from the futures contract")
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--export-json", default=None, help="optional path to dump full results as JSON")
    args = ap.parse_args()

    fut = resolve_front_month_future("NIFTY")
    fut_ltp = get_live_fut_ltp(fut["instrument_key"])
    lot_size = args.lot_size or fut["lot_size"]

    rows = fetch_live_chain(args.symbol)
    expiries_all = merged_expiry_dates(rows)
    reference_day = resolve_reference_trading_day()
    try:
        expiry1, expiry2, expiry3 = resolve_expiry_triplet(reference_day.isoformat(), expiries_all)
    except ValueError as e:
        print(f"{e} — aborting.")
        sys.exit(1)
    capture_ts = rows[0]["ts"]

    dte = (date.fromisoformat(expiry1) - reference_day).days
    today_ist = datetime.now(timezone.utc).astimezone(IST).date()
    is_live_session = reference_day == today_ist

    k_strike = args.k_strike if args.k_strike is not None else floor_strike_100(fut_ltp)

    print(f"Live capture ts={capture_ts}  {fut['trading_symbol']} LTP={fut_ltp}  lot_size={lot_size}")
    print(f"expiry1 = {expiry1}  |  expiry2 = {expiry2}  |  expiry3 = {expiry3}")
    print(f"(merged expiry set seen: {expiries_all})")
    print(f"reference trading day = {reference_day}  (expiry1 DTE={dte})"
          + ("" if is_live_session else "  — market not yet open today, this LTP is last session's close"))
    print(f"k_strike (fut floored to nearest 100) = {int(k_strike)}")

    lookup = build_ltp_lookup(rows)
    name = f"{int(k_strike)}/{int(k_strike - args.leg_gap)}"
    result = simulate_strategy(k_strike, args.leg_gap, expiry1, expiry2, expiry3,
                                lookup, fut_ltp, args.move_range, args.move_step, lot_size)
    if result is None:
        print(f"\n=== {name}: missing entry LTP data at one or more legs — aborting ===")
        sys.exit(1)
    print_strategy(name, result)

    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump({
                "capture_ts": capture_ts, "fut_ltp": fut_ltp,
                "fut_trading_symbol": fut["trading_symbol"], "fut_expiry": fut["expiry"],
                "expiry1": expiry1, "expiry2": expiry2, "expiry3": expiry3,
                "reference_day": reference_day.isoformat(), "dte": dte, "is_live_session": is_live_session,
                "lot_size": lot_size, "strategy": result,
            }, f, indent=2)
        print(f"\nExported to {args.export_json}")


if __name__ == "__main__":
    main()
