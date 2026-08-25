#!/usr/bin/env python3
"""
One-time (safely re-runnable) backfill: computes margin_required/margin_final
for every recommended_trade that was created by a roll (parent_trade_id IS
NOT NULL) but has no margin yet — roll_recommended_trade() never set margin
on the new row it creates, a gap fixed going forward by calling
recalculate_recommendation_margin() right after each auto-roll in
live/triggers.py's _do_auto_roll(). This backfills every rolled trade created
before that fix.

Uses the exact same recalculate_recommendation_margin() the live fix calls,
so it hits Upstox for a live SPAN margin quote per trade — only meaningful
for still-open rolled trades (an exited trade's margin isn't shown anywhere
in the UI), and best run while the market/Upstox session is up.

Usage:
    cd backend && python scripts/backfill_rolled_trade_margins.py            # dry run
    cd backend && python scripts/backfill_rolled_trade_margins.py --apply    # write changes
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import get_connection  # noqa: E402


def main(apply: bool) -> None:
    conn = get_connection()
    trades = conn.execute("""
        SELECT id, symbol, trigger_name, status FROM recommended_trades
        WHERE parent_trade_id IS NOT NULL AND margin_required IS NULL
        ORDER BY entry_time ASC
    """).fetchall()
    conn.close()

    if not trades:
        print("Nothing to backfill — every rolled trade already has a margin.")
        return

    from live.manual_trade import recalculate_recommendation_margin

    updated = 0
    for trade_id, symbol, trigger_name, status in trades:
        print(f"  trade_id={trade_id}  {symbol}  {trigger_name}  status={status} ... ", end="")
        if not apply:
            print("(dry run — skipped)")
            continue
        margin_final = recalculate_recommendation_margin(trade_id)
        if margin_final is not None:
            print(f"margin_final={margin_final:,.0f}")
            updated += 1
        else:
            print("failed — left NULL (see error above, if any)")

    if apply:
        print(f"\nApplied. {updated}/{len(trades)} rolled trade(s) got a margin.")
    else:
        print(f"\nDry run — {len(trades)} rolled trade(s) would be attempted. Re-run with --apply to write changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write the changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
