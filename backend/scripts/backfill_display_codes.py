#!/usr/bin/env python3
"""
One-time (safely re-runnable) backfill: assigns display_code ({MON}{YY}-{N},
e.g. AUG26-1) to every recommended_trade that doesn't have one yet — needed
for trades created before this field existed. New trades get it automatically
at creation (open_recommended_trade / roll_recommended_trade in db/queries.py).

Processes trades oldest-first by entry_time, so the per-(month,year) numbering
comes out in the same order those trades actually happened. Each trade's
expiry is taken from its own legs (original entry legs if present, else
whatever legs it has) — every trade row maps to exactly one expiry cycle by
design, so this is unambiguous.

Skips trades with no legs at all (nothing to derive an expiry from — will
just keep display_code=NULL) or non-F&O legs with no expiry_str (e.g. a
manual equity trade) — same as new trades, this is best-effort, nothing
depends on display_code being set.

Usage:
    cd backend && python scripts/backfill_display_codes.py            # dry run
    cd backend && python scripts/backfill_display_codes.py --apply    # write changes
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.init_db import get_connection  # noqa: E402
from datetime import datetime  # noqa: E402


def _prefix(expiry_str: str | None) -> str | None:
    if not expiry_str:
        return None
    try:
        dt = datetime.strptime(expiry_str, "%d %b %Y")
    except ValueError:
        return None
    return dt.strftime("%b").upper() + dt.strftime("%y")


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
        row = conn.execute(
            "SELECT expiry_str FROM trade_legs WHERE trade_id = ? AND expiry_str IS NOT NULL "
            "ORDER BY id LIMIT 1",
            (trade_id,),
        ).fetchone()
        prefix = _prefix(row[0] if row else None)
        if not prefix:
            print(f"  trade_id={trade_id}: no usable expiry_str on its legs — skipped")
            continue

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
