# Drishti — main entry point
# ============================================================
#  Usage:
#    python main.py bootstrap          — first-time DB seed
#    python main.py sync               — end-of-day data sync
#    python main.py verify             — check DB health
#    python main.py live               — start live market poller
#    python main.py live --force       — run poller outside market hours
#    python main.py bootstrap RELIANCE — bootstrap one symbol
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
        from bootstrap.yfinance_loader import run_bootstrap
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

    else:
        print(f"Unknown command: {command}")
        print("Valid commands: bootstrap, sync, verify, init, live")
        sys.exit(1)


if __name__ == "__main__":
    main()
