# One-off correction for the two NIFTY prediction games from 2026-09-23 that
# resolved against wrong data (see docs/prd/nifty-daily-prediction-games.md
# and memory project_1d_candle_sync_stale_bug — Upstox's Historical API never
# returns the current trading day, which the sync pipeline didn't account
# for until this same fix). Confirmed correct values via Upstox's separate
# Intraday Candle Data API, independent of the buggy sync: open=23352.15,
# close=23446.80.
#
# This is a ONE-OFF historical correction, not a reusable tool — the root
# cause is fixed (sync/daily_sync.py now calls the intraday API), so this
# situation shouldn't recur. Delete this file after running it once.
#
# ============================================================
#  BEFORE RUNNING ON PROD:
#    1. Back up the DB first:
#         cp backend/data/drishti.db backend/data/drishti.db.bak-$(date +%Y%m%d-%H%M%S)
#    2. Run the SELECT-only dry run first to confirm the game IDs and
#       current (wrong) values match what you expect:
#         python3 scripts/correct_2026_09_23_games.py --dry-run
#    3. Only then run for real:
#         python3 scripts/correct_2026_09_23_games.py --apply
# ============================================================

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(f".env.{os.environ.get('FLASK_ENV', 'production')}")

from db.init_db import get_connection
from db.queries import _award_credits_tx

TARGET_DATE_LABEL = "23 Sep 2026"   # matches how the games' own titles format the date
OPEN_CORRECT  = 23352.15
CLOSE_CORRECT = 23446.80
WIN_THRESHOLD = 10


def find_game(conn, auto_kind: str):
    """Find the specific auto-created game for the target date, by title —
    not by a hardcoded id, since prod's ids won't match any local pull."""
    row = conn.execute(
        "SELECT * FROM games WHERE auto_kind=? AND title LIKE ?",
        (auto_kind, f"%{TARGET_DATE_LABEL}%"),
    ).fetchone()
    return dict(row) if row else None


def score_entries(conn, game_id: int, correct_value: float):
    entries = conn.execute(
        "SELECT id, user_id, entry_data, submitted_at, credits_won FROM game_entries WHERE game_id=?",
        (game_id,),
    ).fetchall()
    scored = []
    for e in entries:
        predicted = json.loads(e["entry_data"])["predicted_price"]
        score = abs(float(predicted) - correct_value)
        scored.append({
            "id": e["id"], "user_id": e["user_id"], "score": score,
            "ts": e["submitted_at"], "old_credits_won": e["credits_won"],
        })
    scored.sort(key=lambda x: (x["score"], x["ts"]))
    return scored


def correct_game(conn, game, correct_value: float, label: str, apply: bool):
    game_id = game["id"]
    print(f"\n=== Game #{game_id} \"{game['title']}\" ({label}) ===")
    print(f"    current result_value = {game['result_value']}  ->  correct = {correct_value}")

    scored = score_entries(conn, game_id, correct_value)
    winner_count = game["winner_count"]
    reward_pool = game["reward_pool"]

    for i, s in enumerate(scored):
        rank = i + 1
        within = s["score"] <= WIN_THRESHOLD
        won = reward_pool if (rank <= winner_count and within) else 0
        delta = won - s["old_credits_won"]
        marker = f"  <- credit delta {delta:+d}" if delta != 0 else ""
        print(f"    user {s['user_id']:>4}  score={s['score']:7.2f}  rank={rank:2d}  "
              f"credits_won={won:3d} (was {s['old_credits_won']}){marker}")

        if apply:
            conn.execute(
                "UPDATE game_entries SET score=?, rank=?, credits_won=? WHERE id=?",
                (s["score"], rank, won, s["id"]),
            )
            if delta != 0:
                _award_credits_tx(
                    conn, s["user_id"], delta, "game_reward_correction",
                    str(game_id),
                    f"Correction: rank #{rank} in game #{game_id} after real {label} confirmed "
                    f"(sync bug fix — see docs/prd/nifty-daily-prediction-games.md)",
                )

    if apply:
        conn.execute("UPDATE games SET result_value=? WHERE id=?", (str(correct_value), game_id))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    g.add_argument("--apply", action="store_true", help="actually write the correction")
    args = ap.parse_args()

    conn = get_connection()

    open_game = find_game(conn, "nifty_next_open")
    close_game = find_game(conn, "nifty_today_close")

    if not open_game or not close_game:
        print(f"Could not find both games for '{TARGET_DATE_LABEL}' "
              f"(open found: {bool(open_game)}, close found: {bool(close_game)}). "
              f"Nothing changed. Check TARGET_DATE_LABEL matches the real title.")
        conn.close()
        return

    correct_game(conn, open_game, OPEN_CORRECT, "open", apply=args.apply)
    correct_game(conn, close_game, CLOSE_CORRECT, "close", apply=args.apply)

    if args.apply:
        conn.commit()
        print("\nApplied and committed.")
    else:
        print("\nDry run only — nothing written. Re-run with --apply to actually correct it.")

    conn.close()


if __name__ == "__main__":
    main()
