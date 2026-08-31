#!/usr/bin/env python3
"""
Safety-net backfill: computes margin_required/margin_final for any still-open
recommended_trade created by a roll (parent_trade_id IS NOT NULL) that has no
margin yet.

As of the 2026-08 fix, live/triggers.py's _do_auto_roll() computes margin for
the new legs BEFORE calling roll_recommended_trade(), and passes it straight
into the same atomic INSERT that creates the row — mirroring how a genuinely
fresh entry gets its margin (a roll is really two lifecycle events, exit +
new entry; parent_trade_id is lineage tracking only, never a reason to defer
margin computation). That closes the original gap: roll_recommended_trade()
used to insert a bare row and rely on a separate follow-up UPDATE
(recalculate_recommendation_margin()) that could fail or run too late — that
two-step pattern is exactly how trades 29/30/32/33/34 ended up permanently
NULL (see scripts/backfill_exited_rolled_trade_margins.py for that incident
and why, once a rolled trade has since exited, this script can no longer
help it — get_current_legs() nets a closed trade's legs to zero).

This script now only matters as a safety net for the one remaining failure
mode: the atomic get_margin() call at roll time itself failing (Upstox rate
limit/outage) — _do_auto_roll sends a Telegram alert when that happens, and
this is how you'd retry it, for as long as the trade is still open.

Uses the exact same recalculate_recommendation_margin() the live path calls,
so it hits Upstox for a live SPAN margin quote per trade — only meaningful
for still-open rolled trades, and best run while the market/Upstox session
is up.

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
