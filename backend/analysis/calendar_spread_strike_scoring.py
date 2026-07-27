"""
Drishti — NIFTY CE Calendar-Spread Strike Scoring
==================================================
Recommends a strike for the sell-near/buy-far CE calendar spread
(SELL the nearer weekly-cadence expiry, BUY the next one out, same strike)
and shows how its debit is expected to behave across a downside spot range
and across the near leg's remaining days-to-expiry (DTE).

Method: docs/prd/calendar-spread-strike-scoring.md +
        .claude/skills/calendar-spread-debit-proxy/SKILL.md
Data:   option_chain_5m, populated by live/option_chain_capture.py
        (docs/prd/option-chain-capture.md)

DTE snapshots come from two different sources, both folded into one
{dte: (ts, near_expiry, far_expiry)} dict:
  - DTE = (near_leg expiry - today) days: the REAL, unproxied point — today's
    actual near_leg/far_leg (SELL/BUY) legs, no substitution needed, because
    the near leg genuinely sits at that many days to expiry right now.
  - Every other DTE (lower — what near_leg will look like as it counts down
    in future days): PROXIED via the 'imminent' contract (cadence_dates[0]),
    which is already further along its own countdown today or was on a past
    capture day — paired with near_leg standing in as the future leg, exactly
    the calendar-spread-debit-proxy skill's method.

Usage:
    python analysis/calendar_spread_strike_scoring.py --support 23800 --resistance 24500
    python analysis/calendar_spread_strike_scoring.py --support 23800 --resistance 24500 --symbol NIFTY50

This is a read-only analysis tool. It does not write to any table, does not
place or suggest trades to recommended_trades, and is never invoked by the
live poller — run it standalone whenever you want a fresh recommendation.
"""

import sys
import os
import argparse
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.queries import (
    get_merged_cadence_dates,
    get_option_chain_ltp,
    get_latest_option_chain_ts,
    get_option_chain_capture_days,
)

SYMBOL_DEFAULT = "NIFTY50"
OPT_TYPE = "CE"
STRIKE_STEP = 100          # candidate strikes are multiples of this
CAPTURED_GRID = 50         # option_chain_5m captures every 50 pts — proxy-strike lookups must round to this
NUM_CANDIDATES = 8         # how many 100-pt strikes above spot to evaluate, mirrors the 8-nearest-strike rule


def _round_to_grid(x: float, grid: int = CAPTURED_GRID) -> float:
    return round(x / grid) * grid


def _spot_at(symbol: str, ts: str) -> float | None:
    from db.init_db import get_connection
    conn = get_connection()
    cur = conn.execute("SELECT spot_ltp FROM option_chain_5m WHERE symbol=? AND ts=? LIMIT 1",
                        (symbol, ts))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def _debit(symbol: str, near_expiry: str, far_expiry: str, strike: float, ts: str) -> float | None:
    near = get_option_chain_ltp(symbol, OPT_TYPE, near_expiry, strike, ts)
    far = get_option_chain_ltp(symbol, OPT_TYPE, far_expiry, strike, ts)
    if near is None or far is None:
        return None
    return round(far - near, 2)


def build_dte_snapshots(symbol: str, imminent: str, near_leg: str, far_leg: str,
                         ts_entry: str) -> dict[int, tuple[str, str, str]]:
    """
    {DTE: (ts, near_expiry, far_expiry)}.

    Real point (no proxy): DTE = days from today to near_leg's own expiry —
    today's actual near_leg/far_leg prices at ts_entry are ground truth for
    that DTE, not an estimate.

    Proxy points: one per UTC calendar day with captured data for the
    'imminent' contract (cadence_dates[0]), using that day's latest ts.
    DTE = (imminent_expiry - capture_day).days. imminent/near_leg stand in
    for near_leg/far_leg at that future DTE. Days with DTE < 0 are dropped.

    If a proxy DTE happens to collide with the real DTE (shouldn't normally
    happen since imminent and near_leg are different contracts), the real
    point wins — ground truth over proxy.
    """
    snapshots: dict[int, tuple[str, str, str]] = {}

    expiry_d = date.fromisoformat(imminent)
    for day_str in get_option_chain_capture_days(symbol, imminent):
        capture_d = date.fromisoformat(day_str)
        dte = (expiry_d - capture_d).days
        if dte < 0:
            continue
        ts = get_latest_option_chain_ts(symbol, date_prefix=day_str)
        if ts:
            snapshots[dte] = (ts, imminent, near_leg)

    today_d = date.fromisoformat(ts_entry[:10])
    near_leg_d = date.fromisoformat(near_leg)
    real_dte = (near_leg_d - today_d).days
    snapshots[real_dte] = (ts_entry, near_leg, far_leg)  # ground truth, overrides any proxy collision

    return snapshots


def candidate_strikes(spot: float, resistance: float, max_n: int = NUM_CANDIDATES) -> list[float]:
    """
    100-pt strikes from just above spot up to `resistance` (inclusive) — resistance
    is the upper bound of the view, so strikes beyond it aren't evaluated. Capped at
    max_n strikes even if resistance is far above spot, to keep the candidate set
    to the near-the-money strikes this strategy actually cares about.
    """
    first = _round_to_grid(spot, STRIKE_STEP)
    if first <= spot:
        first += STRIKE_STEP
    strikes = []
    k = first
    while k <= resistance and len(strikes) < max_n:
        strikes.append(k)
        k += STRIKE_STEP
    if not strikes:
        # resistance sits below the first OTM strike — fall back to that one strike
        # so the tool still returns something, but this is a signal the inputs conflict.
        strikes = [first]
    return strikes


def spot_scenarios(support: float, top: float, step: int = STRIKE_STEP) -> list[float]:
    """Descending list of 100-pt spot levels from `top` down to (and including) `support`."""
    levels = []
    lvl = _round_to_grid(top, step)
    while lvl >= support:
        levels.append(lvl)
        lvl -= step
    if not levels or levels[-1] != support:
        levels.append(support)
    return levels


def no_move_pnl(symbol, strike, entry_debit, dte_snapshots) -> dict[int, float | None]:
    """P&L (vs entry) at each available DTE if spot stays at its entry level (strike not shifted)."""
    result = {}
    for dte, (ts, near_expiry, far_expiry) in dte_snapshots.items():
        debit = _debit(symbol, near_expiry, far_expiry, strike, ts)
        result[dte] = round(debit - entry_debit, 2) if debit is not None else None
    return result


def worst_case_for_strike(symbol, strike, spot_entry, entry_debit, support, dte_snapshots) -> dict:
    """
    Worst-case (minimum) projected debit for `strike` across every available DTE
    snapshot, evaluated at the support spot level — the maximum-adverse-case cell.
    Also carries whether the strike is even sound at baseline (no_move_ok) — a
    strike that already loses with spot flat is not "safe," just thin/cheap, and
    must not be recommended on worst-case-loss numbers alone.
    """
    worst_by_dte = {}
    shift = spot_entry - support
    for dte, (ts, near_expiry, far_expiry) in dte_snapshots.items():
        proxy_strike = _round_to_grid(strike + shift)
        worst_by_dte[dte] = _debit(symbol, near_expiry, far_expiry, proxy_strike, ts)
    valid = {d: v for d, v in worst_by_dte.items() if v is not None}

    no_move = no_move_pnl(symbol, strike, entry_debit, dte_snapshots)
    no_move_valid = {d: v for d, v in no_move.items() if v is not None}
    no_move_ok = bool(no_move_valid) and all(v >= 0 for v in no_move_valid.values())

    if not valid:
        return {"worst_debit": None, "worst_dte": None, "loss_pts": None, "loss_pct": None,
                "no_move_ok": no_move_ok, "no_move_pnl": no_move}
    worst_dte, worst_debit = min(valid.items(), key=lambda kv: kv[1])
    loss_pts = round(entry_debit - worst_debit, 2)
    loss_pct = round(100 * loss_pts / entry_debit, 1) if entry_debit else None
    return {"worst_debit": worst_debit, "worst_dte": worst_dte, "loss_pts": loss_pts, "loss_pct": loss_pct,
            "no_move_ok": no_move_ok, "no_move_pnl": no_move}


def print_strike_detail(symbol, strike, spot_entry, ts_entry, near_leg, far_leg, dte_snapshots, support):
    r1 = get_option_chain_ltp(symbol, OPT_TYPE, near_leg, strike, ts_entry)
    r2 = get_option_chain_ltp(symbol, OPT_TYPE, far_leg, strike, ts_entry)
    if r1 is None or r2 is None:
        print(f"  strike {strike}: missing entry leg data at ts={ts_entry}, skipping detail")
        return
    entry_debit = round(r2 - r1, 2)

    print(f"\n=== Strike {strike}  (entry spot={spot_entry}, ts={ts_entry}) ===")
    print(f"  SELL leg {near_leg} CE {strike} ltp = {r1}")
    print(f"  BUY  leg {far_leg} CE {strike} ltp = {r2}")
    print(f"  ENTRY DEBIT = {r2} - {r1} = {entry_debit}")

    print(f"\n  -- No-move projection (spot stays at entry level, strike NOT shifted) --")
    for dte in sorted(dte_snapshots, reverse=True):
        ts_d, near_expiry, far_expiry = dte_snapshots[dte]
        debit = _debit(symbol, near_expiry, far_expiry, strike, ts_d)
        source = "REAL (today's actual legs)" if near_expiry == near_leg else f"proxy via {near_expiry}"
        if debit is None:
            print(f"    DTE={dte}: no data")
            continue
        pnl = round(debit - entry_debit, 2)
        flag = "OK" if pnl >= 0 else "LOSS"
        print(f"    DTE={dte} [{source}]: projected debit={debit}  P&L vs entry={pnl:+.2f}  [{flag}]")

    print(f"\n  -- Spot-fall grid: support({support}) .. strike({strike}), step {STRIKE_STEP} --")
    levels = spot_scenarios(support, strike)
    header = "spot_level".rjust(11) + "".join(f"DTE={d}".rjust(10) for d in sorted(dte_snapshots, reverse=True))
    print("   " + header)
    breakeven_notes = []
    for level in levels:
        shift = spot_entry - level
        proxy_strike = _round_to_grid(strike + shift)
        row = [f"{level:>11}"]
        for dte in sorted(dte_snapshots, reverse=True):
            ts_d, near_expiry, far_expiry = dte_snapshots[dte]
            debit = _debit(symbol, near_expiry, far_expiry, proxy_strike, ts_d)
            if debit is None:
                row.append("no-data".rjust(10))
                continue
            pnl = round(debit - entry_debit, 2)
            row.append(f"{pnl:+.2f}".rjust(10))
            if pnl < 0:
                breakeven_notes.append((level, dte))
        print("   " + "".join(row))

    if breakeven_notes:
        worst_level = min(l for l, _ in breakeven_notes)
        print(f"\n  Exit/roll guidance: P&L turns negative at or below spot {max(l for l, _ in breakeven_notes)} "
              f"(worst tested level {worst_level}). Once spot has fallen through that level, decay does not "
              f"recover the position — roll strike/expiry rather than hold.")


def print_all_candidates_grid(symbol, strikes, entry_debits, spot_entry, near_leg,
                               support, resistance, dte_snapshots):
    """
    One P&L table per available DTE, rows = spot levels (support..resistance),
    columns = every candidate strike.

    Note on the diagonal (spot_level == K): the strike-shift proxy collapses
    to today's actual ATM strike regardless of which K column you're in,
    because `proxy_strike = K + (entry_spot - scenario_spot)` reduces to
    `entry_spot` when scenario_spot == K — every candidate strike converges
    to the SAME projected future debit there (spot rallying to meet strike K
    makes K the new ATM, and today's actual ATM debit is the best available
    stand-in for that, independent of K's absolute value). The P&L still
    differs per column along that diagonal purely because each strike's
    entry debit differs — cheaper entries (higher K here) show larger
    upside P&L against the same projected future value, not because the
    future value itself is strike-dependent.
    """
    levels = spot_scenarios(support, resistance)
    col_w = 22
    for dte in sorted(dte_snapshots, reverse=True):
        ts_d, near_expiry, far_expiry = dte_snapshots[dte]
        source = "REAL, today's actual legs" if near_expiry == near_leg else f"proxy via {near_expiry}"
        print(f"\n--- Projected debit / P&L vs entry, DTE={dte} [{source}] (spot {support}..{resistance}"
              f" — entry spot was {spot_entry}) ---")
        print("  cell format: projected_debit / P&L_vs_entry")
        header = "spot_level".rjust(11) + "".join(
            f"K={k:.0f} (entry={entry_debits.get(k)})".rjust(col_w) for k in strikes)
        print(header)
        for level in levels:
            shift = spot_entry - level
            row = [f"{level:>11}"]
            for k in strikes:
                proxy_strike = _round_to_grid(k + shift)
                debit = _debit(symbol, near_expiry, far_expiry, proxy_strike, ts_d)
                entry_debit = entry_debits.get(k)
                if debit is None or entry_debit is None:
                    row.append("no-data".rjust(col_w))
                    continue
                pnl = round(debit - entry_debit, 2)
                row.append(f"{debit:.2f} / {pnl:+.2f}".rjust(col_w))
            print("".join(row))


def main():
    ap = argparse.ArgumentParser(description="NIFTY CE calendar-spread strike scoring")
    ap.add_argument("--support", type=float, required=True, help="downside spot support level, e.g. 23800")
    ap.add_argument("--resistance", type=float, required=True, help="upside spot resistance level, e.g. 24500")
    ap.add_argument("--symbol", default=SYMBOL_DEFAULT)
    args = ap.parse_args()

    symbol = args.symbol
    support, resistance = args.support, args.resistance

    cadence = get_merged_cadence_dates(symbol)
    if len(cadence) < 3:
        print(f"Not enough cadence dates captured for {symbol} yet ({cadence}) — need at least 3. "
              f"Insufficient data, aborting.")
        return
    imminent, near_leg, far_leg = cadence[0], cadence[1], cadence[2]

    ts_entry = get_latest_option_chain_ts(symbol)
    if not ts_entry:
        print(f"No option_chain_5m data for {symbol}. Insufficient data, aborting.")
        return
    spot_entry = _spot_at(symbol, ts_entry)

    dte_snapshots = build_dte_snapshots(symbol, imminent, near_leg, far_leg, ts_entry)

    print(f"Symbol: {symbol}   Entry ts: {ts_entry}   Entry spot: {spot_entry}")
    print(f"Cadence dates: {cadence}")
    print(f"  imminent (proxy source) = {imminent}")
    print(f"  SELL leg                = {near_leg}")
    print(f"  BUY leg                 = {far_leg}")
    print(f"Support: {support}   Resistance: {resistance}")
    dte_labels = []
    for dte in sorted(dte_snapshots, reverse=True):
        _, ne, _ = dte_snapshots[dte]
        dte_labels.append(f"{dte}{'(real)' if ne == near_leg else '(proxy)'}")
    print(f"Available DTE snapshots: {dte_labels}"
          f"  (more proxy DTE values fill in automatically as daily captures accumulate)")

    strikes = candidate_strikes(spot_entry, resistance)
    first_otm = _round_to_grid(spot_entry, STRIKE_STEP)
    if first_otm <= spot_entry:
        first_otm += STRIKE_STEP
    if resistance < first_otm:
        print(f"\nWarning: resistance ({resistance}) is below the first OTM 100-strike ({first_otm}) — "
              f"only evaluating that one strike. Check your support/resistance inputs.")
    print(f"\nCandidate strikes (100-pt multiples, spot .. resistance, capped at {NUM_CANDIDATES}): {strikes}")

    print(f"\n{'strike':>8} {'entry':>8} {'no_move_ok':>11} {'worst_debit':>12} {'worst_DTE':>10} "
          f"{'loss_pts':>9} {'loss_pct':>9}")
    scored = []
    entry_debits = {}
    for K in strikes:
        r1 = get_option_chain_ltp(symbol, OPT_TYPE, near_leg, K, ts_entry)
        r2 = get_option_chain_ltp(symbol, OPT_TYPE, far_leg, K, ts_entry)
        if r1 is None or r2 is None:
            print(f"{K:>8}   missing captured data at this strike, skipped")
            continue
        entry_debit = round(r2 - r1, 2)
        entry_debits[K] = entry_debit
        wc = worst_case_for_strike(symbol, K, spot_entry, entry_debit, support, dte_snapshots)
        scored.append((K, entry_debit, wc))
        wd = wc["worst_debit"]
        print(f"{K:>8} {entry_debit:>8} {str(wc['no_move_ok']):>11} {str(wd):>12} {str(wc['worst_dte']):>10} "
              f"{str(wc['loss_pts']):>9} {str(wc['loss_pct'])+'%' if wc['loss_pct'] is not None else 'None':>9}")

    if entry_debits and dte_snapshots:
        print_all_candidates_grid(symbol, list(entry_debits.keys()), entry_debits, spot_entry,
                                   near_leg, support, resistance, dte_snapshots)

    scored_valid = [s for s in scored if s[2]["loss_pts"] is not None]
    if not scored_valid:
        print("\nNo strike had enough data to score. Insufficient data — try again once more days are captured.")
        return

    # A strike that already loses with spot flat isn't "safe," it's just thin —
    # only rank strikes that are sound at baseline (no_move_ok) by worst-case loss.
    sound = [s for s in scored_valid if s[2]["no_move_ok"]]
    if not sound:
        print("\nNo candidate strike is profitable in the no-move case at any available DTE — "
              "none of these strikes are structurally sound for this spread right now. "
              "Not recommending a strike; widen the candidate range or re-check entry timing.")
        return

    best_rupee = min(sound, key=lambda s: s[2]["loss_pts"])
    best_pct = min(sound, key=lambda s: s[2]["loss_pct"])
    print(f"\n(Ranking restricted to strikes where no-move P&L is >= 0 at every available DTE — "
          f"{len(sound)} of {len(scored_valid)} candidates qualify.)")
    print(f"Best by min rupee loss at support {support}: strike {best_rupee[0]} "
          f"(entry {best_rupee[1]}, worst-case loss {best_rupee[2]['loss_pts']} pts)")
    print(f"Best by min % loss at support {support}: strike {best_pct[0]} "
          f"(entry {best_pct[1]}, worst-case loss {best_pct[2]['loss_pct']}%)")
    if best_rupee[0] != best_pct[0]:
        print("These disagree — rupee-loss and percentage-loss rankings favor different strikes "
              "(cheaper entries always show larger % swings for the same rupee move). "
              "Recommending by rupee loss below since that's the direct capital-at-risk measure; "
              "override with the %-best strike if that's the more relevant lens for your sizing.")

    recommended = best_rupee[0]
    print(f"\n{'='*70}\nRECOMMENDED STRIKE: {recommended}\n{'='*70}")
    print_strike_detail(symbol, recommended, spot_entry, ts_entry, near_leg, far_leg, dte_snapshots, support)


if __name__ == "__main__":
    main()
