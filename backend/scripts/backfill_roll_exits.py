#!/usr/bin/env python3
"""
One-time (safely re-runnable) data fix for recommended_trades that were
rolled under the OLD auto-roll mechanism — where the closing leg of a roll
was recorded as action='entry' instead of action='exit', so that roll's
realized P&L never showed up anywhere while the trade stayed open.

Scans every OPEN recommended_trade for instrument_keys where BUY and SELL
lots exactly net to zero across its action='entry' legs (a closed roll pair),
and retags the later (closing) leg's action to 'exit' in place. Trade status
is never touched — the trade stays 'open', reflecting whatever's genuinely
still live after the fix.

Safe to re-run: once a pair is backfilled, its closing leg is no longer
action='entry', so a second run naturally finds nothing left to fix for it.

Does NOT need to run before the new roll mechanism (triggers.py's
_do_auto_roll) works correctly going forward — get_current_legs() already
nets action='entry' legs correctly regardless of this backfill. This script
only restores visibility into P&L that already happened under the old
mechanism, for trades that already rolled at least once under it.

Usage:
    cd backend && python scripts/backfill_roll_exits.py            # dry run — prints what it WOULD change
    cd backend && python scripts/backfill_roll_exits.py --apply    # actually writes the changes

Back up the database first:
    cp data/drishti.db data/drishti.db.bak_$(date +%Y%m%d_%H%M%S)
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import get_connection  # noqa: E402


def find_and_fix(apply: bool) -> None:
    conn = get_connection()  # sqlite3.Row rows — index access below works fine

    open_trades = conn.execute(
        "SELECT id, symbol, trigger_name FROM recommended_trades WHERE status = 'open'"
    ).fetchall()

    total_pairs = 0
    for trade_id, symbol, trigger_name in open_trades:
        rows = conn.execute(
            "SELECT id, side, instrument_type, instrument_key, strike, expiry_str, "
            "lots, lot_size, price, ts FROM trade_legs "
            "WHERE trade_id = ? AND action = 'entry' ORDER BY id",
            (trade_id,),
        ).fetchall()

        by_instrument: dict[str, list[tuple]] = {}
        for row in rows:
            key = row[3]  # instrument_key
            by_instrument.setdefault(key, []).append(row)

        for key, group in by_instrument.items():
            buy_lots  = sum(r[6] for r in group if r[1] == "BUY")
            sell_lots = sum(r[6] for r in group if r[1] == "SELL")
            if buy_lots != sell_lots or len(group) < 2:
                continue  # still live (net non-zero), or nothing to close against

            group_sorted = sorted(group, key=lambda r: r[0])  # by leg id
            close_leg = group_sorted[-1]
            leg_id, side, itype, ikey, strike, expiry, lots, lot_size, price, ts = close_leg

            print(f"  trade_id={trade_id} ({symbol}/{trigger_name})  "
                  f"leg id={leg_id}  {itype} {ikey}  {side} {lots}x{lot_size} @{price}  "
                  f"ts={ts}   entry -> exit")
            total_pairs += 1
            if apply:
                conn.execute("UPDATE trade_legs SET action = 'exit' WHERE id = ?", (leg_id,))

    if apply:
        conn.commit()
        print(f"\nApplied. {total_pairs} leg(s) retagged entry -> exit.")
    else:
        print(f"\nDry run — {total_pairs} leg(s) would be retagged. Re-run with --apply to write changes.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write the changes (default: dry run)")
    args = parser.parse_args()
    find_and_fix(apply=args.apply)
