#!/usr/bin/env python3
"""
One-time (safely re-runnable) backfill for rolled trades that have ALREADY
exited/rolled-further with margin still NULL — recommended_trades rows with
parent_trade_id IS NOT NULL, margin_at_entry IS NULL, and status != 'open'.

Root cause (2026-08 incident, trade ids 29/30/32/33/34): roll_recommended_
trade() has never set margin on the new row it creates — _do_auto_roll
(live/triggers.py) calls recalculate_recommendation_margin() right after
every roll to fill it in while the trade is still live. That call was added
2026-08-25 (commit a9599ef); trades 29/30/32/33/34 were all rolled by the
poller *before* that fix was running, and had already exited by the time
anyone could re-run scripts/backfill_rolled_trade_margins.py against them.

That sibling script (backfill_rolled_trade_margins.py) can't help here: it
calls recalculate_recommendation_margin(), which prices CURRENT open legs via
get_current_legs() — for an exited trade the entry and exit legs net to zero,
so it always returns None without even calling Upstox.

This script instead prices each trade's ORIGINAL ENTRY legs (get_original_
entry_legs, unnetted) directly through Upstox's live SPAN margin ("what-if")
calculator — the same live/upstox_client.get_margin() call recalculate_
recommendation_margin() itself uses. Two important caveats:

  1. This is Upstox's CURRENT-day margin quote for that exact instrument/qty/
     side combination, not a time machine — it is not literally the margin
     that would have applied on the trade's actual entry day. This mirrors
     the same acknowledged limitation as scripts/backfill_margin_at_entry.py
     (which explicitly refuses to call Upstox for historical margin at all).
     We accept this because there is no other source of a real number, and
     it is captured the same way every other margin_at_entry value in this
     table is: a live Upstox quote for those legs, not a hand-guessed one.

  2. If the entry legs' option/future contract has since EXPIRED, Upstox's
     margin API rejects the request outright (400 Bad Request — the
     instrument is no longer listed). In that case there is no way to get a
     real number at all, ever, and the row is left NULL on purpose rather
     than fabricated. (This is exactly what happens for trades 29/30 in the
     2026-08 incident — their Aug-2026-expiry legs expired before this
     script could run; only 32/33/34, on a not-yet-expired Oct-2026 contract,
     are recoverable.)

Usage:
    cd backend && python scripts/backfill_exited_rolled_trade_margins.py            # dry run
    cd backend && python scripts/backfill_exited_rolled_trade_margins.py --apply    # write changes

Requires a valid UPSTOX_ACCESS_TOKEN (same as any other live Upstox call).
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import get_connection  # noqa: E402
from db.queries import get_original_entry_legs  # noqa: E402


def main(apply: bool) -> None:
    conn = get_connection()
    trades = conn.execute("""
        SELECT id, symbol, trigger_name, status, parent_trade_id, entry_time, exit_time
        FROM recommended_trades
        WHERE parent_trade_id IS NOT NULL
          AND margin_at_entry IS NULL
          AND status != 'open'
        ORDER BY entry_time ASC
    """).fetchall()

    if not trades:
        print("Nothing to backfill — every exited rolled trade already has margin_at_entry.")
        conn.close()
        return

    from live.upstox_client import get_margin

    updated, failed = 0, 0
    for trade_id, symbol, trigger_name, status, parent_id, entry_time, exit_time in trades:
        print(f"  trade_id={trade_id}  {symbol}  {trigger_name}  status={status}  "
              f"parent={parent_id}  entry={entry_time}  exit={exit_time}")

        legs = get_original_entry_legs(trade_id)
        margin_input = [
            {
                "instrument_key":   l["instrument_key"],
                "transaction_type": l["side"],
                "quantity":         l["lots"] * (l["lot_size"] or 1),
                "price":            l["price"],
            }
            for l in legs if l["instrument_key"] and l["lot_size"]
        ]
        if not margin_input:
            print(f"    -> no priceable entry legs found, skipping")
            failed += 1
            continue

        try:
            m = get_margin(margin_input)
        except Exception as e:
            print(f"    -> Upstox margin call failed: {e}  (likely an expired "
                  f"contract — this trade may be permanently unrecoverable)")
            failed += 1
            continue

        margin_required = m.get("required_margin")
        margin_final = m.get("final_margin")
        if margin_required is None:
            print(f"    -> Upstox returned no margin value, skipping")
            failed += 1
            continue

        print(f"    -> margin_required={margin_required:,.2f}  margin_final={margin_final:,.2f}")
        if apply:
            conn.execute(
                "UPDATE recommended_trades "
                "SET margin_required=?, margin_final=?, margin_at_entry=? "
                "WHERE id=?",
                (margin_required, margin_final, margin_final, trade_id),
            )
            updated += 1
        else:
            print(f"    -> (dry run — skipped)")

    if apply:
        conn.commit()
        print(f"\nApplied. {updated} updated, {failed} left NULL "
              f"(out of {len(trades)} candidate trade(s)).")
    else:
        print(f"\nDry run — {len(trades)} candidate trade(s), re-run with --apply to write changes.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
