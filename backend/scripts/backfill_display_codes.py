#!/usr/bin/env python3
"""
One-time (safely re-runnable) backfill: assigns display_code ({MON}{YY}-{N},
e.g. AUG26-1, or EQ-{N} for a pure equity trade) to every recommended_trade
that doesn't have one yet — needed for trades created before this field
existed. New trades get it automatically at creation (open_recommended_trade
/ roll_recommended_trade in db/queries.py).

Processes trades oldest-first by entry_time, so the per-prefix numbering
comes out in the same order those trades actually happened. Each trade's
prefix is the NEAREST expiry among ALL of its legs (a calendar spread's
near/far legs aren't necessarily inserted in expiry order, so picking just
one leg — e.g. "whichever comes first" — would be fragile) via
db.queries.display_code_prefix(), or "EQ" if none of its legs have an expiry
at all (a pure equity trade).

Usage:
    cd backend && python scripts/backfill_display_codes.py            # dry run
    cd backend && python scripts/backfill_display_codes.py --apply    # write changes
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import get_connection  # noqa: E402
from db.queries import display_code_prefix  # noqa: E402


def main(apply: bool) -> None:
    conn = get_connection()
    trades = conn.execute(
        "SELECT id FROM recommended_trades WHERE display_code IS NULL ORDER BY entry_time ASC"
    ).fetchall()

    # Seed the per-prefix counter from codes already assigned (e.g. a
    # previous --apply run, or new trades created since), so numbering
    # continues correctly rather than starting over from 1. Kept in memory
    # and incremented as we go — querying the DB fresh per trade would give
    # wrong (duplicate) numbers in a dry run, since nothing's written yet to
    # count, and would still require re-querying after every single write in
    # --apply mode.
    counters: dict[str, int] = {}
    for (existing_code,) in conn.execute(
        "SELECT display_code FROM recommended_trades WHERE display_code IS NOT NULL"
    ):
        prefix, _, n = existing_code.rpartition("-")
        if prefix and n.isdigit():
            counters[prefix] = max(counters.get(prefix, 0), int(n))

    assigned = 0
    for (trade_id,) in trades:
        leg_rows = conn.execute(
            "SELECT expiry_str FROM trade_legs WHERE trade_id = ?", (trade_id,)
        ).fetchall()
        if not leg_rows:
            print(f"  trade_id={trade_id}: no legs at all — skipped")
            continue
        prefix = display_code_prefix([r[0] for r in leg_rows])

        counters[prefix] = counters.get(prefix, 0) + 1
        code = f"{prefix}-{counters[prefix]}"

        print(f"  trade_id={trade_id}: display_code = {code}")
        assigned += 1
        if apply:
            conn.execute(
                "UPDATE recommended_trades SET display_code = ? WHERE id = ?",
                (code, trade_id),
            )

    if apply:
        conn.commit()
        print(f"\nApplied. {assigned} trade(s) assigned a display_code.")
    else:
        print(f"\nDry run — {assigned} trade(s) would be assigned. Re-run with --apply to write changes.")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write the changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
