#!/usr/bin/env python3
"""
One-time (safely re-runnable) fix for recommended_trades rolled under the
OLD auto-roll mechanism (before the close+reopen-linked-trade redesign) —
combines what were previously two separate scripts (backfill_roll_exits.py +
split_rolled_trades.py) into one pass per trade:

  1. Backfill: find instrument_keys where BUY and SELL lots exactly net to
     zero across the trade's action='entry' legs (a closed roll pair, e.g.
     an auto-roll's old leg bought back), and retag the later (closing) leg
     to action='exit'. This is what makes that roll's P&L real, recorded
     data instead of invisible.

  2. Split: using the exit leg(s) from step 1 (plus any that already existed
     from a prior partial run), close the trade for real — status='exited',
     with a clean entry+exit-only leg history — and open a new trade linked
     via parent_trade_id holding just whatever's still genuinely live,
     status='open'. Matches exactly the shape the new roll mechanism
     (triggers.py's _do_auto_roll / db.queries.roll_recommended_trade)
     produces going forward, instead of leaving one row mixing closed
     history with a live position.

Also retags the old trade's now-half-empty 'auto_roll' trade_adjustments
rows to adj_type='exit' (matching close_recommended_trade()'s own
convention), so the split trade doesn't show a redundant "Adjustment"
section with a leg matched against itself at $0 P&L.

Safe to re-run: an already-fixed trade is 'exited' and won't be picked up
again (only 'open' trades are scanned); a trade with nothing to backfill or
split is left untouched.

Usage:
    cd backend && python scripts/fix_old_rolled_trades.py            # dry run
    cd backend && python scripts/fix_old_rolled_trades.py --apply    # write changes

Back up the database first:
    cp data/drishti.db data/drishti.db.bak_$(date +%Y%m%d_%H%M%S)
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import get_connection  # noqa: E402
from db.queries import get_current_legs  # noqa: E402


def fix_trade(conn, trade_id: int, apply: bool):
    row = conn.execute(
        "SELECT symbol, trigger_name, entry_level, exit_level FROM recommended_trades WHERE id = ?",
        (trade_id,),
    ).fetchone()
    if not row:
        return None
    symbol, trigger_name, entry_level, exit_level = row

    # --- step 1: backfill net-zero pairs (entry -> exit) ---
    entry_rows = conn.execute(
        "SELECT id, side, instrument_type, instrument_key, strike, expiry_str, "
        "lots, lot_size, price, ts FROM trade_legs "
        "WHERE trade_id = ? AND action = 'entry' ORDER BY id",
        (trade_id,),
    ).fetchall()

    by_instrument: dict[str, list[tuple]] = {}
    for r in entry_rows:
        by_instrument.setdefault(r[3], []).append(r)

    closed_any = False
    latest_price = latest_ts = None
    for key, group in by_instrument.items():
        buy_lots  = sum(r[6] for r in group if r[1] == "BUY")
        sell_lots = sum(r[6] for r in group if r[1] == "SELL")
        if buy_lots != sell_lots or len(group) < 2:
            continue  # still live (net non-zero), or nothing to close against

        close_leg = sorted(group, key=lambda r: r[0])[-1]
        leg_id, side, itype, ikey, strike, expiry, lots, lot_size, price, ts = close_leg

        print(f"  trade_id={trade_id} ({symbol}/{trigger_name})  backfill: leg id={leg_id}  "
              f"{itype} {ikey}  {side} {lots}x{lot_size} @{price}  ts={ts}   entry -> exit")
        closed_any = True
        if latest_ts is None or ts >= latest_ts:
            latest_price, latest_ts = price, ts
        if apply:
            conn.execute("UPDATE trade_legs SET action = 'exit' WHERE id = ?", (leg_id,))

    # Also account for exit legs that already existed (e.g. a previous
    # partial run, or a genuine prior partial exit) when picking which
    # price/time to close the trade with below.
    existing_exit = conn.execute(
        "SELECT price, ts FROM trade_legs WHERE trade_id = ? AND action = 'exit' ORDER BY id DESC LIMIT 1",
        (trade_id,),
    ).fetchone()
    if existing_exit and (latest_ts is None or existing_exit[1] >= latest_ts):
        latest_price, latest_ts = existing_exit

    if latest_ts is None:
        return None  # never rolled at all — nothing to backfill or split

    # --- step 2: split off whatever's still live ---
    # Netting doesn't care whether the closing leg is tagged entry or exit
    # (same side/lots either way), so this is correct even in a dry run
    # where step 1's retag above was only printed, not written yet.
    live_legs = get_current_legs(trade_id)
    if not live_legs:
        return None  # fully closed already (or nothing left live) — nothing to split

    print(f"  trade_id={trade_id}: close as exited (exit_ltp={latest_price}, exit_time={latest_ts}); "
          f"split off {len(live_legs)} still-live leg(s) into a new trade:")
    for l in live_legs:
        print(f"    leg id={l['id']}  {l['side']} {l['instrument_type']} {l['instrument_key']}  "
              f"{l['lots']}x{l['lot_size']} @{l['price']}")

    if not apply:
        return "would-fix"

    conn.execute(
        "UPDATE recommended_trades SET status = 'exited', exit_ltp = ?, exit_time = ? WHERE id = ?",
        (latest_price, latest_ts, trade_id),
    )
    conn.execute(
        "UPDATE trade_adjustments SET adj_type = 'exit' WHERE trade_id = ? AND adj_type != 'exit'",
        (trade_id,),
    )

    new_entry_ltp = live_legs[0]["price"]
    cur = conn.execute("""
        INSERT INTO recommended_trades
            (trigger_name, symbol, parent_trade_id, entry_level, entry_ltp, entry_time, exit_level, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
    """, (trigger_name, symbol, trade_id, entry_level, new_entry_ltp, latest_ts, exit_level))
    new_trade_id = cur.lastrowid

    for l in live_legs:
        # adjustment_id=NULL — from the new trade's perspective this is its
        # own original entry leg, not an adjustment (see split_rolled_trades.py
        # history for why leaving the old adjustment_id in place breaks
        # get_original_entry_legs() / get_trade_adjustments() for the new trade).
        conn.execute(
            "UPDATE trade_legs SET trade_id = ?, adjustment_id = NULL WHERE id = ?",
            (new_trade_id, l["id"]),
        )

    print(f"    -> new trade id={new_trade_id}")
    return new_trade_id


def main(apply: bool) -> None:
    conn = get_connection()
    open_trades = conn.execute("SELECT id FROM recommended_trades WHERE status = 'open'").fetchall()

    results = []
    for (trade_id,) in open_trades:
        result = fix_trade(conn, trade_id, apply)
        if result:
            results.append((trade_id, result))

    if apply:
        conn.commit()
        print(f"\nApplied. {len(results)} trade(s) fixed (backfilled + split).")
    else:
        print(f"\nDry run — {len(results)} trade(s) would be fixed. Re-run with --apply to write changes.")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write the changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
