#!/usr/bin/env python3
"""
Interactive: walk every OPEN recommended_trade with no risk_level set and
prompt for one, one at a time. Unlike the other scripts/backfill_*.py
scripts, risk_level is a subjective judgment call (low/mid/high/very_high)
that no query can compute — this just makes clearing the backlog fast,
showing enough context (symbol, trigger, legs, note) per trade to decide
from, and writes each answer immediately so quitting partway never loses
progress already made.

If a trade's trigger has a configured risk_level in config.py (currently
just NIFTY500_MULTI -> "high"), it's offered as the default for plain
Enter — trades from that trigger opened/rolled after the config was added
already get stamped automatically; this is only for the backlog from
before that existed.

Usage:
    cd backend && python scripts/set_open_rec_risk_levels.py

At each prompt: low/mid/high/very_high (or short forms l/m/h/v), Enter to
accept the suggested default (if shown), 's' to skip, 'q' to quit.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from db.init_db import get_connection  # noqa: E402
from db.queries import get_current_legs  # noqa: E402

VALID = ["low", "mid", "high", "very_high"]
SHORT = {"l": "low", "m": "mid", "h": "high", "v": "very_high"}
SUGGESTED = {t["name"]: t["risk_level"] for t in config.TRIGGERS if t.get("risk_level")}


def fmt_leg(leg: dict) -> str:
    strike = f"{int(leg['strike']):,} " if leg.get("strike") else ""
    expiry = leg.get("expiry_str") or ""
    return f"{leg['side']} {strike}{leg['instrument_type']} {expiry}".strip()


def main() -> None:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, display_code, symbol, trigger_name, note, entry_time "
        "FROM recommended_trades WHERE status='open' AND risk_level IS NULL "
        "ORDER BY entry_time"
    ).fetchall()
    conn.close()

    if not rows:
        print("Nothing to do — every open recommendation already has a risk_level.")
        return

    print(f"{len(rows)} open recommendation(s) with no risk_level.\n"
          f"Enter low/mid/high/very_high (or l/m/h/v), 's' to skip, 'q' to quit.\n")

    updated = skipped = 0
    for i, (rec_id, code, symbol, trigger_name, note, entry_time) in enumerate(rows, 1):
        legs = get_current_legs(rec_id)
        suggested = SUGGESTED.get(trigger_name)

        print(f"[{i}/{len(rows)}] id={rec_id}  #{code or rec_id}  {symbol}  ({trigger_name})")
        if note:
            print(f"    note: {note}")
        for leg in legs:
            print(f"    - {fmt_leg(leg)}")
        print(f"    entered: {entry_time}")

        prompt = "    risk level"
        if suggested:
            prompt += f" [Enter = {suggested}]"
        prompt += ": "

        value = None
        while True:
            raw = input(prompt).strip().lower()
            if raw == "" and suggested:
                value = suggested
            elif raw in ("s", "skip"):
                value = None
                break
            elif raw in ("q", "quit"):
                print(f"\nStopped early. {updated} updated, {skipped} skipped, "
                      f"{len(rows) - i} left untouched.")
                return
            else:
                value = SHORT.get(raw, raw)
                if value not in VALID:
                    print(f"    invalid — enter one of {', '.join(VALID)} "
                          f"(or l/m/h/v), s to skip, q to quit")
                    continue
            break

        if value is None:
            skipped += 1
            print("    skipped\n")
            continue

        conn = get_connection()
        conn.execute("UPDATE recommended_trades SET risk_level=? WHERE id=?", (value, rec_id))
        conn.commit()
        conn.close()
        updated += 1
        print(f"    -> set to {value}\n")

    print(f"Done. {updated} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
