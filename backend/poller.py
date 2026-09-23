# Drishti — main entry point
# ============================================================
#  Usage:
#    python poller.py bootstrap          — first-time DB seed
#    python poller.py sync               — end-of-day data sync
#    python poller.py verify             — check DB health
#    python poller.py live               — start live market poller
#    python poller.py live --force       — run poller outside market hours
#    python poller.py bootstrap RELIANCE — bootstrap one symbol
#    python poller.py analysis           — run & send daily NIFTY analysis now
#    python poller.py analysis --print   — print to terminal without sending
#    python poller.py games open         — manually run the market-open game
#                                           step (close entries on yesterday
#                                           evening's NIFTY open-prediction
#                                           game — not resolved yet, create
#                                           today's close-prediction game)
#    python poller.py games cutoff       — manually run the close-game entry
#                                           cutoff step (close entries on
#                                           today's NIFTY close-prediction
#                                           game — not resolved yet either)
#    python poller.py games eod          — manually run the EOD game step
#                                           (resolve BOTH of today's NIFTY
#                                           games from the real official
#                                           candles_1d open/close, create the
#                                           next trading day's open-
#                                           prediction game)
# All three are idempotent (safe to re-run — see docs/prd/nifty-daily-
# prediction-games.md) and normally fire automatically inside `live` at
# 09:15/15:00/16:00; this is the manual escape hatch (a missed run, or
# testing without waiting for real market hours).
# ============================================================

import sys
import os


def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(1)

    command = args[0].lower()
    symbols = args[1:] if len(args) > 1 else None

    if command == "bootstrap":
        from bootstrap.upstox_loader import run_bootstrap
        run_bootstrap(symbols)

    elif command == "sync":
        from sync.daily_sync import run_daily_sync
        run_daily_sync(symbols)

    elif command == "verify":
        from utils.verify_db import verify_all
        verify_all()

    elif command == "init":
        from db.init_db import init_db
        init_db()

    elif command == "live":
        from live.poller import run_live
        force = "--force" in args
        run_live(force=force)

    elif command == "analysis":
        import re
        from live.daily_analysis import build_analysis, format_report, run_daily_analysis
        if "--print" in args:
            a   = build_analysis()
            msg = format_report(a)
            print(re.sub(r"<[^>]+>", "", msg))   # strip HTML for terminal
        else:
            run_daily_analysis()                  # build + send to Telegram

    elif command == "games":
        from live.poller import (
            _run_market_open_game_tasks, _run_close_entry_cutoff_task, _run_eod_game_tasks,
        )
        action = symbols[0] if symbols else None
        if action == "open":
            _run_market_open_game_tasks()
        elif action == "cutoff":
            _run_close_entry_cutoff_task()
        elif action == "eod":
            _run_eod_game_tasks()
        else:
            print("Usage: python poller.py games open|cutoff|eod")
            sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        print("Valid commands: bootstrap, sync, verify, init, live, analysis, games")
        sys.exit(1)


if __name__ == "__main__":
    main()
