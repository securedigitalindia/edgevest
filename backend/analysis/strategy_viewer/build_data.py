"""Build the per-day data for one strategy for the shareable artifact page.
usage (from backend/):  venv/bin/python analysis/strategy_viewer/build_data.py STRATEGY_ID OUT.json
Thin wrapper: the engine and the strategy definitions live in backend/strategies/ (day_view.py, day_strategies.py) and are
shared with the dashboard's Day view, so a number can never differ between the two."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db.init_db import get_connection
from strategies import day_view
from strategies.day_strategies import DAY_STRATEGIES


def main(sid, out_path):
    S = DAY_STRATEGIES[sid]; conn = get_connection()
    listing = day_view.list_days(conn, sid)
    out = dict(id=sid, name=S["label"], desc=S["description"], lot=S["lot"], step=S["entry"]["step"], near=S["entry"]["near"],
               variants=S["variants"], offs=S["offs"],
               legs=[dict(role=l["role"], qty=l["qty"], thin_oi=l["thin_oi"], expiry=l["expiry"]) for l in S["legs"]],
               data_to=(listing["as_of"] or "").replace(" IST", ""), days={})
    for e in listing["days"]:
        rec = day_view.compute_day(conn, sid, e["date"])
        if rec:
            out["days"][e["date"]] = rec
            print(e["date"], rec["touch"], flush=True)
    json.dump(out, open(out_path, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
