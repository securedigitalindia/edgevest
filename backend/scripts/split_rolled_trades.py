#!/usr/bin/env python3
"""
Splits a trade that was rolled under the OLD mechanism (kept as one row,
closing leg retagged action='exit' by backfill_roll_exits.py) into the shape
the new roll mechanism (triggers.py's _do_auto_roll / roll_recommended_trade)
would have produced: the original trade fully exited (containing only its
original entry legs + that roll's exit legs), and a new trade linked via
parent_trade_id holding just the still-live legs, status='open'.

MUST run after backfill_roll_exits.py --apply — this script only finds
something to split once action='exit' legs actually exist for a trade.

Skips (no-op) any trade with no action='exit' legs (never rolled, or backfill
hasn't run yet) or no still-live legs (already fully closed for real).

Usage:
    cd backend && python scripts/split_rolled_trades.py            # dry run
    cd backend && python scripts/split_rolled_trades.py --apply    # write changes

Back up the database first:
    cp data/drishti.db data/drishti.db.bak_$(date +%Y%m%d_%H%M%S)
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import get_connection  # noqa: E402
from db.queries import get_current_legs  # noqa: E402


def split_trade(conn, trade_id: int, apply: bool):
    row = conn.execute(
        "SELECT trigger_name, symbol, entry_level, exit_level FROM recommended_trades WHERE id = ?",
        (trade_id,),
    ).fetchone()
    if not row:
        return None
    trigger_name, symbol, entry_level, exit_level = row

    live_legs = get_current_legs(trade_id)
    if not live_legs:
        return None  # nothing still open to split off

    exit_row = conn.execute(
        "SELECT price, ts FROM trade_legs WHERE trade_id = ? AND action = 'exit' ORDER BY id DESC LIMIT 1",
        (trade_id,),
    ).fetchone()
    if not exit_row:
        return None  # no roll recorded yet (backfill hasn't run, or never rolled) — nothing to split
    exit_price, exit_ts = exit_row

    print(f"  trade_id={trade_id} ({symbol}/{trigger_name}): "
          f"close as exited (exit_ltp={exit_price}, exit_time={exit_ts}); "
          f"split off {len(live_legs)} still-live leg(s) into a new trade:")
    for l in live_legs:
        print(f"    leg id={l['id']}  {l['side']} {l['instrument_type']} {l['instrument_key']}  "
              f"{l['lots']}x{l['lot_size']} @{l['price']}")

    if not apply:
        return "would-split"

    conn.execute(
        "UPDATE recommended_trades SET status = 'exited', exit_ltp = ?, exit_time = ? WHERE id = ?",
        (exit_price, exit_ts, trade_id),
    )
    # The old 'auto_roll' trade_adjustments rows on this trade now only
    # describe half a roll (their other leg just moved to the new trade) —
    # get_trade_adjustments() excludes adj_type='exit' rows, so retagging
    # these the same way close_recommended_trade() tags its own exit
    # adjustment removes the now-redundant "Adjustment" section (which would
    # otherwise show that leg matched against itself, a $0 PnL row) without
    # touching the leg rows themselves — they're still valid exit legs.
    conn.execute(
        "UPDATE trade_adjustments SET adj_type = 'exit' WHERE trade_id = ? AND adj_type != 'exit'",
        (trade_id,),
    )
    new_entry_ltp = live_legs[0]["price"]
    cur = conn.execute("""
        INSERT INTO recommended_trades
            (trigger_name, symbol, parent_trade_id, entry_level, entry_ltp, entry_time, exit_level, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
    """, (trigger_name, symbol, trade_id, entry_level, new_entry_ltp, exit_ts, exit_level))
    new_trade_id = cur.lastrowid

    for l in live_legs:
        # adjustment_id=NULL — from the new trade's perspective this is its
        # own original entry leg, not an adjustment. Leaving the old
        # adjustment_id in place would point at a trade_adjustments row
        # belonging to the OLD trade_id, which breaks both
        # get_original_entry_legs() (requires adjustment_id IS NULL to count
        # as an original leg) and get_trade_adjustments() (looks up by this
        # trade's own id) — silently leaving the new trade's legs invisible
        # everywhere except get_current_legs().
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
        result = split_trade(conn, trade_id, apply)
        if result:
            results.append((trade_id, result))

    if apply:
        conn.commit()
        print(f"\nApplied. {len(results)} trade(s) split.")
    else:
        print(f"\nDry run — {len(results)} trade(s) would be split. Re-run with --apply to write changes.")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write the changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
