#!/usr/bin/env python3
"""
Drishti — Manual Trade Web UI
Run:  python trade_server.py
Opens http://localhost:5555 in your browser.
"""
import sys
import os
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
PORT = 5555


# ─────────────────────────────────────────────────────────
# API: instrument search
# ─────────────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify(results=[])
    from live.fo_instruments import search_instruments
    raw = search_instruments(q)[:12]
    results = []
    for r in raw:
        if r["strike"]:
            label = f"{r['symbol']}  {int(r['strike']):,} {r['instrument_type']}  {r['expiry_str']}"
        else:
            label = f"{r['symbol']}  {r['instrument_type']}  {r['expiry_str']}"
        if r["weekly"]:
            label += "  (weekly)"
        results.append({
            "label":           label,
            "symbol":          r["symbol"],
            "instrument_type": r["instrument_type"],
            "strike":          r["strike"],
            "expiry_str":      r["expiry_str"],
            "weekly":          r["weekly"],
        })
    return jsonify(results=results)


# ─────────────────────────────────────────────────────────
# API: brokers / traders / accounts
# ─────────────────────────────────────────────────────────

@app.route("/api/brokers", methods=["GET", "POST"])
def api_brokers():
    from db.queries import get_brokers, add_broker
    if request.method == "POST":
        name = (request.json or {}).get("name", "").strip()
        if not name:
            return jsonify(ok=False, error="name is required"), 400
        try:
            bid = add_broker(name)
            return jsonify(ok=True, id=bid)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 400
    return jsonify(brokers=get_brokers())


@app.route("/api/traders", methods=["GET", "POST"])
def api_traders():
    from db.queries import get_traders, add_trader
    if request.method == "POST":
        data   = request.json or {}
        name   = data.get("name", "").strip()
        mobile = data.get("mobile", "")
        note   = data.get("note", "")
        if not name:
            return jsonify(ok=False, error="name is required"), 400
        tid = add_trader(name, mobile, note)
        return jsonify(ok=True, id=tid)
    return jsonify(traders=get_traders())


@app.route("/api/accounts", methods=["GET", "POST"])
def api_accounts():
    from db.queries import get_accounts, add_account
    if request.method == "POST":
        data       = request.json or {}
        trader_id  = data.get("trader_id")
        broker_id  = data.get("broker_id")
        account_no = data.get("account_no", "")
        label      = data.get("label", "")
        if not trader_id or not broker_id:
            return jsonify(ok=False, error="trader_id and broker_id are required"), 400
        aid = add_account(trader_id, broker_id, account_no, label)
        return jsonify(ok=True, id=aid)
    return jsonify(accounts=get_accounts())


# ─────────────────────────────────────────────────────────
# API: trades
# ─────────────────────────────────────────────────────────

@app.route("/api/trades")
def api_trades():
    from db.queries import get_all_open_trades, get_trade_legs
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")

    account_id = request.args.get("account_id", type=int)
    trades = get_all_open_trades(account_id=account_id)
    out = []
    for t in trades:
        legs = [l for l in get_trade_legs(t["id"]) if l["action"] == "entry"]
        try:
            dt = datetime.strptime(t["entry_time"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc).astimezone(IST)
            entry_ist = dt.strftime("%d %b %Y  %H:%M IST")
        except Exception:
            entry_ist = t["entry_time"]
        out.append({
            "id":            t["id"],
            "symbol":        t["symbol"],
            "entry_ist":     entry_ist,
            "legs":          legs,
            "account_id":    t["account_id"],
            "account_label": t["account_label"],
            "trader_name":   t["trader_name"],
            "broker_name":   t["broker_name"],
        })
    return jsonify(trades=out)


@app.route("/api/trades/create", methods=["POST"])
def api_create():
    data       = request.json or {}
    symbol     = data.get("symbol", "")
    legs       = data.get("legs", [])
    note       = data.get("note", "")
    account_id = data.get("account_id")
    if not symbol or not legs:
        return jsonify(ok=False, error="symbol and legs are required"), 400
    try:
        from live.manual_trade import add_manual_trade
        trade_id = add_manual_trade(symbol, legs, note, account_id=account_id)
        return jsonify(ok=True, trade_id=trade_id)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


@app.route("/api/prices", methods=["POST"])
def api_prices():
    keys = (request.json or {}).get("keys", [])
    if not keys:
        return jsonify({})
    try:
        from live.upstox_client import get_ltp
        return jsonify(get_ltp(keys))
    except Exception:
        return jsonify({})


@app.route("/api/spot")
def api_spot():
    from live.fo_instruments import SPOT_IKEYS
    try:
        from live.upstox_client import get_ltp
        prices = get_ltp(list(SPOT_IKEYS.values()))
        return jsonify({
            sym: prices[ikey]
            for sym, ikey in SPOT_IKEYS.items()
            if ikey in prices
        })
    except Exception:
        return jsonify({})


@app.route("/api/trades/<int:trade_id>/exit", methods=["POST"])
def api_exit(trade_id):
    data   = request.json or {}
    prices = data.get("prices", [])
    note   = data.get("note", "")
    if not prices:
        return jsonify(ok=False, error="prices are required"), 400
    try:
        from live.manual_trade import close_manual_trade
        close_manual_trade(trade_id, prices, note)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


# ─────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────

def _preload():
    print("  Loading F&O instrument index from Upstox...", flush=True)
    try:
        from live.fo_instruments import _ensure_loaded
        _ensure_loaded()
        print("  Instrument index ready.\n", flush=True)
    except Exception as e:
        print(f"  [warning] instrument preload failed: {e}\n", flush=True)


if __name__ == "__main__":
    print(f"\n{'='*52}")
    print("  Drishti  —  Trade Manager")
    print(f"  http://localhost:{PORT}")
    print(f"{'='*52}\n")

    _preload()

    threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
