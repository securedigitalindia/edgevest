#!/usr/bin/env python3
"""
One-time (safely re-runnable) backfill: populates margin_at_entry for every
recommended_trade created before that column existed (docs/prd/monthly-
recommendation-report.md) — those rows have margin_at_entry IS NULL, which
makes them contribute 0 to the Monthly Report's margin series/peak, even
though they clearly had a real margin at entry (margin_required/margin_final
were already being captured long before margin_at_entry existed).

There's no way to retroactively ask Upstox what a trade's SPAN margin was on
its actual entry day — that's live market data, not something that can be
recomputed after the fact. So this uses the best available substitute: each
row's own already-stored margin_final (falling back to margin_required if
margin_final is NULL), which was itself captured close to the trade's entry
in every case that predates this feature. No Upstox API call, no network
dependency — purely copies existing columns into the new one.

Usage:
    cd backend && python scripts/backfill_margin_at_entry.py            # dry run
    cd backend && python scripts/backfill_margin_at_entry.py --apply    # write changes
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import get_connection  # noqa: E402


def main(apply: bool) -> None:
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, symbol, status, margin_required, margin_final
        FROM recommended_trades
        WHERE margin_at_entry IS NULL
          AND (margin_required IS NOT NULL OR margin_final IS NOT NULL)
        ORDER BY entry_time ASC
    """).fetchall()

    if not rows:
        print("Nothing to backfill — every trade with a known margin already has margin_at_entry.")
        conn.close()
        return

    updated = 0
    for trade_id, symbol, status, margin_required, margin_final in rows:
        value = margin_final if margin_final is not None else margin_required
        print(f"  trade_id={trade_id}  {symbol}  status={status}  -> margin_at_entry={value:,.0f}", end="")
        if apply:
            conn.execute(
                "UPDATE recommended_trades SET margin_at_entry = ? WHERE id = ?",
                (value, trade_id),
            )
            updated += 1
            print()
        else:
            print("  (dry run — skipped)")

    if apply:
        conn.commit()
        print(f"\nApplied. {updated}/{len(rows)} trade(s) backfilled.")
    else:
        print(f"\nDry run — {len(rows)} trade(s) would be backfilled. Re-run with --apply to write changes.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
