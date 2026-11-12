"""Strategy definitions now live in backend/strategies/day_strategies.py (shared with the dashboard's Day view).
Edit them there; this module only re-exports them for readability. See README.md."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from strategies.day_strategies import DAY_STRATEGIES as STRATEGIES  # noqa: E402,F401
