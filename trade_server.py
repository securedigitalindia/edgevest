#!/usr/bin/env python3
"""
Drishti — Trade Manager Web UI
Run:  python trade_server.py
"""
import sys
import os
import threading
import webbrowser
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for, abort)
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
PORT = 5555

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ["GOOGLE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# ─────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────

def current_user() -> dict | None:
    return session.get("user")

def require_login(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify(error="Unauthorized"), 401
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapped

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify(error="Unauthorized"), 401
                return redirect(url_for("login"))
            if user["role"] not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(error="Forbidden"), 403
                return abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator

def require_subscription(f):
    """For client-role users: redirect to /subscribe if no valid active subscription."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user and user["role"] == "client":
            from db.queries import is_subscription_valid
            if not is_subscription_valid(user["id"]):
                if request.path.startswith("/api/"):
                    return jsonify(error="No active subscription"), 402
                return redirect(url_for("subscribe_page", expired=1))
        return f(*args, **kwargs)
    return wrapped

def is_admin(user=None):
    u = user or current_user()
    return u and u["role"] in ("super_admin", "admin")

def is_super_admin(user=None):
    u = user or current_user()
    return u and u["role"] == "super_admin"

def _ist_str(utc_str: str) -> str:
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
        return dt.strftime("%d %b %Y  %H:%M IST")
    except Exception:
        return utc_str


# ─────────────────────────────────────────────────────────
# Session refresh — keeps role always current
# ─────────────────────────────────────────────────────────

_NO_REFRESH = {"login", "auth_google", "auth_callback", "logout", "static",
               "api_prices", "api_spot"}

@app.before_request
def refresh_session():
    import time
    user = session.get("user")
    if not user or request.endpoint in _NO_REFRESH:
        return
    # Only re-query the DB at most once per 60 seconds to avoid hitting the DB
    # on every API call (page load fires several concurrent requests).
    last = session.get("_session_refreshed_at", 0)
    if time.time() - last < 60:
        return
    from db.queries import get_user_by_google_id
    fresh = get_user_by_google_id(user["google_id"])
    if fresh:
        session["user"] = fresh
        session["_session_refreshed_at"] = time.time()
    else:
        session.clear()


# ─────────────────────────────────────────────────────────
# Auth routes
# ─────────────────────────────────────────────────────────

@app.route("/login")
def login():
    return redirect(url_for("index"))

@app.route("/auth/google")
def auth_google():
    redirect_uri = url_for("auth_callback", _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/auth/callback")
def auth_callback():
    token    = google.authorize_access_token()
    userinfo = token.get("userinfo") or google.userinfo()
    from db.queries import upsert_user, get_user_trading_profile
    user = upsert_user(
        google_id = userinfo["sub"],
        email     = userinfo["email"],
        name      = userinfo["name"],
        picture   = userinfo.get("picture", ""),
    )
    if not user["active"]:
        return redirect(url_for("index", error="deactivated"))
    session["user"] = user
    if user["role"] == "client":
        profile = get_user_trading_profile(user["id"])
        if not profile or not profile.get("setup_done"):
            return redirect(url_for("profile_setup"))
        from db.queries import is_subscription_valid, expire_stale_subscriptions
        expire_stale_subscriptions()
        if not is_subscription_valid(user["id"]):
            return redirect(url_for("subscribe_page"))
    return redirect(url_for("app_index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ─────────────────────────────────────────────────────────
# API: current user
# ─────────────────────────────────────────────────────────

@app.route("/api/me")
@require_login
def api_me():
    return jsonify(user=current_user())


# ─────────────────────────────────────────────────────────
# API: users (super_admin only)
# ─────────────────────────────────────────────────────────

@app.route("/api/users")
@require_role("super_admin", "admin")
def api_users():
    from db.queries import get_all_users
    return jsonify(users=get_all_users())

@app.route("/api/users/<int:uid>/role", methods=["POST"])
@require_role("super_admin")
def api_user_role(uid):
    role = (request.json or {}).get("role", "")
    if role not in ("super_admin", "admin", "client"):
        return jsonify(ok=False, error="Invalid role"), 400
    from db.queries import update_user_role
    update_user_role(uid, role)
    return jsonify(ok=True)

@app.route("/api/users/<int:uid>/profile", methods=["POST"])
@require_login
def api_user_profile(uid):
    user = current_user()
    if not is_admin() and user["id"] != uid:
        return jsonify(ok=False, error="Forbidden"), 403
    data   = request.json or {}
    mobile = data.get("mobile", "")
    note   = data.get("note", "")
    role   = data.get("role", "")
    from db.queries import update_user_profile, update_user_role
    update_user_profile(uid, mobile, note)
    if role and is_admin():
        valid = {"super_admin", "admin", "client"}
        if role not in valid:
            return jsonify(ok=False, error="Invalid role"), 400
        update_user_role(uid, role)
    return jsonify(ok=True)


# ─────────────────────────────────────────────────────────
# API: subscription plans (admin)
# ─────────────────────────────────────────────────────────

@app.route("/api/plans")
@require_login
def api_plans_list():
    from db.queries import get_all_plans, get_active_plans
    if is_admin():
        return jsonify(plans=get_all_plans())
    return jsonify(plans=get_active_plans())

@app.route("/api/plans", methods=["POST"])
@require_role("super_admin", "admin")
def api_plans_create():
    data = request.json or {}
    name     = data.get("name", "").strip()
    desc     = data.get("description", "").strip()
    price    = int(data.get("price", 0))
    duration = int(data.get("duration_days", 30))
    if not name:
        return jsonify(ok=False, error="name required"), 400
    from db.queries import create_plan
    pid = create_plan(name, desc, price, duration)
    return jsonify(ok=True, id=pid)

@app.route("/api/plans/<int:plan_id>/toggle", methods=["POST"])
@require_role("super_admin", "admin")
def api_plans_toggle(plan_id):
    active = (request.json or {}).get("active", True)
    from db.queries import set_plan_active
    set_plan_active(plan_id, bool(active))
    return jsonify(ok=True)

@app.route("/api/subscriptions")
@require_role("super_admin", "admin")
def api_subscriptions_list():
    from db.queries import get_all_subscriptions
    return jsonify(subscriptions=get_all_subscriptions())


# ─────────────────────────────────────────────────────────
# API: instrument search
# ─────────────────────────────────────────────────────────

@app.route("/api/search")
@require_login
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
        if r.get("lot_size"):
            label += f"  · lot {r['lot_size']}"
        results.append({
            "label":           label,
            "symbol":          r["symbol"],
            "instrument_type": r["instrument_type"],
            "strike":          r["strike"],
            "expiry_str":      r["expiry_str"],
            "weekly":          r["weekly"],
            "lot_size":        r.get("lot_size") or 0,
        })
    return jsonify(results=results)


# ─────────────────────────────────────────────────────────
# API: brokers / accounts
# ─────────────────────────────────────────────────────────

@app.route("/api/brokers", methods=["GET", "POST"])
@require_login
def api_brokers():
    from db.queries import get_brokers, add_broker
    if request.method == "POST":
        if not is_admin():
            return jsonify(ok=False, error="Forbidden"), 403
        name = (request.json or {}).get("name", "").strip()
        if not name:
            return jsonify(ok=False, error="name is required"), 400
        try:
            bid = add_broker(name)
            return jsonify(ok=True, id=bid)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 400
    return jsonify(brokers=get_brokers())


@app.route("/api/accounts", methods=["GET", "POST"])
@require_login
def api_accounts():
    from db.queries import get_accounts, get_accounts_for_user, add_account
    user = current_user()
    if request.method == "POST":
        data       = request.json or {}
        user_id    = data.get("user_id")
        broker_id  = data.get("broker_id")
        account_no = data.get("account_no", "")
        label      = data.get("label", "")
        if user["role"] == "client":
            user_id = user["id"]
        else:
            return jsonify(ok=False, error="Only clients can add accounts"), 403
        if not broker_id:
            return jsonify(ok=False, error="user_id and broker_id are required"), 400
        try:
            aid = add_account(user_id, broker_id, account_no, label)
            return jsonify(ok=True, id=aid)
        except ValueError as e:
            return jsonify(ok=False, error=str(e)), 400
    if user["role"] == "client":
        return jsonify(accounts=get_accounts_for_user(user["id"]))
    return jsonify(accounts=get_accounts())


# ─────────────────────────────────────────────────────────
# API: recommendations
# ─────────────────────────────────────────────────────────

@app.route("/api/recommendations")
@require_login
def api_recommendations():
    from db.queries import get_all_recommendations, get_current_legs, get_trade_adjustments, get_trade_legs
    recs = get_all_recommendations()
    out  = []
    for r in recs:
        current_legs = get_current_legs(r["id"])
        adjustments  = get_trade_adjustments(r["id"])

        exit_legs, realized_pnl = [], None
        if r["status"] == "exited":
            all_legs   = get_trade_legs(r["id"])
            entry_legs = [l for l in all_legs if l["action"] == "entry" and l["adjustment_id"] is None]
            exit_legs  = [l for l in all_legs if l["action"] == "exit"]
            if entry_legs and exit_legs:
                total, has_pnl = 0.0, False
                for e, x in zip(entry_legs, exit_legs):
                    if e["price"] is not None and x["price"] is not None:
                        qty = e["lots"] * e["lot_size"] if e["lot_size"] else e["lots"]
                        total += (e["price"] - x["price"]) * qty if e["side"] == "SELL" \
                                 else (x["price"] - e["price"]) * qty
                        has_pnl = True
                realized_pnl = total if has_pnl else None

        out.append({
            "id":            r["id"],
            "symbol":        r["symbol"],
            "trigger":       r["trigger_name"],
            "status":        r["status"],
            "entry_ist":     _ist_str(r["entry_time"]),
            "exit_ist":      _ist_str(r["exit_time"]) if r.get("exit_time") else None,
            "account_count": r["account_count"],
            "adj_count":     len(adjustments),
            "legs":          current_legs,
            "exit_legs":     exit_legs,
            "realized_pnl":  realized_pnl,
            "adjustments":   adjustments,
        })
    return jsonify(recommendations=out)


@app.route("/api/recommendations/<int:rec_id>/exit", methods=["POST"])
@require_role("super_admin", "admin")
def api_rec_exit(rec_id):
    from datetime import datetime, timezone
    from db.queries import get_recommendation, get_trade_legs, close_recommended_trade
    trade = get_recommendation(rec_id)
    if not trade:
        return jsonify(ok=False, error="Recommendation not found"), 404
    if trade["status"] != "open":
        return jsonify(ok=False, error="Trade is already closed"), 400
    data       = request.json or {}
    prices     = data.get("prices", [])
    now        = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry_legs = [l for l in get_trade_legs(rec_id) if l["action"] == "entry"]

    if len(prices) != len(entry_legs):
        return jsonify(ok=False, error="Price required for every leg"), 400

    exit_legs = [{**l, "action": "exit", "price": prices[i], "ts": now,
                  "side": "SELL" if l["side"] == "BUY" else "BUY"}
                 for i, l in enumerate(entry_legs)]
    exit_ltp  = prices[0] if prices else trade["entry_ltp"]

    close_recommended_trade(rec_id, exit_ltp, now, exit_legs=exit_legs)
    try:
        from live.alert import send_rec_exit_alert
        exit_info = [{**l, "price": prices[i]} for i, l in enumerate(entry_legs)]
        send_rec_exit_alert(trade["symbol"], exit_info, exit_ltp)
    except Exception as e:
        print(f"  [exit alert failed]  {e}", flush=True)
    return jsonify(ok=True)


@app.route("/api/recommendations/<int:rec_id>/adjust", methods=["POST"])
@require_role("super_admin", "admin")
def api_rec_adjust(rec_id):
    from datetime import datetime, timezone
    from db.queries import get_recommendation, add_trade_adjustment
    trade = get_recommendation(rec_id)
    if not trade:
        return jsonify(ok=False, error="Recommendation not found"), 404
    if trade["status"] != "open":
        return jsonify(ok=False, error="Trade is already closed"), 400

    data = request.json or {}
    note = data.get("note", "")
    legs = data.get("legs", [])

    if not legs:
        return jsonify(ok=False, error="Provide at least one leg"), 400

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        adj_id = add_trade_adjustment(rec_id, "adjustment", note or None, now, legs)
        try:
            from live.alert import send_adjustment_alert
            send_adjustment_alert(trade["symbol"], "adjustment", legs, note)
        except Exception as e:
            print(f"  [adjust alert failed]  {e}", flush=True)
        return jsonify(ok=True, adjustment_id=adj_id)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


@app.route("/api/recommendations/create", methods=["POST"])
@require_role("super_admin", "admin")
def api_rec_create():
    data   = request.json or {}
    symbol = data.get("symbol", "")
    legs   = data.get("legs", [])
    note   = data.get("note", "")
    if not symbol or not legs:
        return jsonify(ok=False, error="symbol and legs are required"), 400
    try:
        from live.manual_trade import add_manual_trade
        trade_id = add_manual_trade(symbol, legs, note)
        return jsonify(ok=True, trade_id=trade_id)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


# ─────────────────────────────────────────────────────────
# API: account trades
# ─────────────────────────────────────────────────────────

@app.route("/api/account-trades")
@require_login
def api_account_trades():
    from db.queries import get_open_account_trades, get_account_trade_legs
    user       = current_user()
    account_id = request.args.get("account_id", type=int)

    if user["role"] == "client":
        from db.queries import get_accounts_for_user
        own_ids = {a["id"] for a in get_accounts_for_user(user["id"])}
        trades  = [t for t in get_open_account_trades()
                   if t["account_id"] in own_ids]
    else:
        trades = get_open_account_trades(account_id=account_id)

    from db.queries import get_pending_adjustments_for_account_trade
    out = []
    for t in trades:
        all_at_legs  = get_account_trade_legs(t["id"])
        exited_keys  = {l["instrument_key"] for l in all_at_legs if l["action"] == "exit"}
        current_legs = [l for l in all_at_legs
                        if l["action"] == "entry" and l["instrument_key"] not in exited_keys]
        pending_adjs = get_pending_adjustments_for_account_trade(t["id"])
        out.append({
            "id":               t["id"],
            "symbol":           t["symbol"] or "—",
            "trigger":          t["trigger_name"],
            "rec_id":           t["recommended_trade_id"],
            "account_id":       t["account_id"],
            "account_label":    t["account_label"] or t["broker_name"] or f"Account {t['account_id']}",
            "trader_name":      t["trader_name"],
            "broker_name":      t["broker_name"],
            "entry_ist":        _ist_str(t["entry_time"]),
            "legs":             current_legs,
            "pending_adj_count": len(pending_adjs),
            "pending_adjustments": pending_adjs,
        })
    return jsonify(trades=out)


@app.route("/api/account-trades/create", methods=["POST"])
@require_login
def api_account_trade_create():
    data       = request.json or {}
    rec_id     = data.get("recommended_trade_id")
    account_id = data.get("account_id")
    symbol     = data.get("symbol", "")
    legs       = data.get("legs", [])
    note       = data.get("note", "")
    user       = current_user()

    if not rec_id:
        return jsonify(ok=False, error="recommended_trade_id is required"), 400
    if not account_id or not symbol or not legs:
        return jsonify(ok=False, error="account_id, symbol and legs are required"), 400

    if is_admin():
        return jsonify(ok=False, error="Admins cannot push to accounts"), 403

    from db.queries import get_accounts_for_user
    own_ids = {a["id"] for a in get_accounts_for_user(user["id"])}
    if account_id not in own_ids:
        return jsonify(ok=False, error="Forbidden — not your account"), 403

    try:
        from live.manual_trade import push_to_account
        at_id = push_to_account(rec_id, account_id, symbol, legs, note)
        return jsonify(ok=True, account_trade_id=at_id)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


@app.route("/api/account-trades/<int:at_id>/adjust", methods=["POST"])
@require_login
def api_account_trade_adjust(at_id):
    from datetime import datetime, timezone
    from db.queries import get_open_account_trades, add_account_adjustment
    data                = request.json or {}
    trade_adjustment_id = data.get("adjustment_id")
    adj_type            = data.get("adj_type", "")
    legs                = data.get("legs", [])
    user                = current_user()

    if not trade_adjustment_id or not legs:
        return jsonify(ok=False, error="adjustment_id and legs are required"), 400

    if user["role"] == "client":
        from db.queries import get_accounts_for_user
        own_ids = {a["id"] for a in get_accounts_for_user(user["id"])}
        trade   = next((t for t in get_open_account_trades() if t["id"] == at_id), None)
        if not trade or trade["account_id"] not in own_ids:
            return jsonify(ok=False, error="Forbidden — not your trade"), 403

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        add_account_adjustment(at_id, trade_adjustment_id, legs, now, adj_type=adj_type)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


@app.route("/api/account-trades/<int:at_id>/exit", methods=["POST"])
@require_login
def api_account_trade_exit(at_id):
    from db.queries import get_open_account_trades
    data   = request.json or {}
    prices = data.get("prices", [])
    note   = data.get("note", "")
    user   = current_user()

    if not prices:
        return jsonify(ok=False, error="prices are required"), 400

    if user["role"] == "client":
        from db.queries import get_accounts_for_user
        own_ids = {a["id"] for a in get_accounts_for_user(user["id"])}
        trade   = next((t for t in get_open_account_trades() if t["id"] == at_id), None)
        if not trade or trade["account_id"] not in own_ids:
            return jsonify(ok=False, error="Forbidden — not your trade"), 403

    try:
        from live.manual_trade import close_account_trade
        close_account_trade(at_id, prices, note)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


@app.route("/api/account-trades/history")
@require_login
def api_account_trades_history():
    from db.queries import get_closed_account_trades
    user       = current_user()
    account_id = request.args.get("account_id", type=int)

    if user["role"] == "client":
        trades = get_closed_account_trades(user_id=user["id"])
    else:
        trades = get_closed_account_trades(account_id=account_id)

    out = []
    for t in trades:
        out.append({
            "id":            t["id"],
            "symbol":        t["symbol"] or "—",
            "trigger":       t["trigger_name"],
            "rec_id":        t["recommended_trade_id"],
            "account_id":    t["account_id"],
            "account_label": t["account_label"] or t["broker_name"] or f"Account {t['account_id']}",
            "trader_name":   t["trader_name"],
            "broker_name":   t["broker_name"],
            "entry_ist":     _ist_str(t["entry_time"]),
            "exit_ist":      _ist_str(t["exit_time"]) if t.get("exit_time") else "—",
            "entry_legs":    t["entry_legs"],
            "exit_legs":     t["exit_legs"],
            "realized_pnl":  t["realized_pnl"],
        })
    return jsonify(trades=out)


# ─────────────────────────────────────────────────────────
# API: prices / spot
# ─────────────────────────────────────────────────────────

@app.route("/api/prices", methods=["POST"])
@require_login
def api_prices():
    keys = (request.json or {}).get("keys", [])
    if not keys:
        return jsonify({})
    from db.queries import get_cached_prices
    prices, ts = get_cached_prices(keys)
    if ts:
        prices["_ts"] = ts
    return jsonify(prices)


@app.route("/api/spot")
@require_login
def api_spot():
    from config import SPOT_IKEYS, SPOT_DISPLAY
    from db.queries import get_cached_prices, get_candles
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    prices, ts = get_cached_prices(list(SPOT_IKEYS.values()))
    IST      = ZoneInfo("Asia/Kolkata")
    today    = datetime.now(timezone.utc).astimezone(IST).date()
    out      = {}

    for sym in SPOT_DISPLAY:
        ikey = SPOT_IKEYS.get(sym)
        if not ikey or ikey not in prices:
            continue
        ltp    = prices[ikey]
        change = None
        try:
            df = get_candles(sym, "1d", 3)
            if not df.empty:
                last_date = df.iloc[-1]["ts"].astimezone(IST).date()
                # If today's candle is already synced, prev_close is the row before it
                prev_close = (df.iloc[-2]["close"] if last_date >= today and len(df) >= 2
                              else df.iloc[-1]["close"])
                change = round(ltp - prev_close, 2)
        except Exception:
            pass
        out[sym] = {"ltp": ltp, "change": change}

    if ts:
        out["_ts"] = ts
    return jsonify(out)


# ─────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    if current_user():
        return redirect(url_for("app_index"))
    return render_template("landing.html")


@app.route("/app")
@require_login
@require_subscription
def app_index():
    return render_template("index.html", user=current_user())


@app.route("/profile/setup")
@require_login
def profile_setup():
    from db.queries import get_user_trading_profile
    profile = get_user_trading_profile(current_user()["id"])
    return render_template("profile_setup.html", user=current_user(), profile=profile)


@app.route("/profile")
@require_login
def profile_page():
    from db.queries import get_user_trading_profile
    profile = get_user_trading_profile(current_user()["id"])
    return render_template("profile.html", user=current_user(), profile=profile)


@app.route("/subscribe")
@require_login
def subscribe_page():
    from db.queries import get_active_plans, get_user_subscription
    plans   = get_active_plans()
    sub     = get_user_subscription(current_user()["id"])
    expired = request.args.get("expired", 0)
    return render_template("subscribe.html", user=current_user(),
                           plans=plans, subscription=sub, expired=expired)


@app.route("/api/subscribe", methods=["POST"])
@require_login
def api_subscribe():
    data    = request.json or {}
    plan_id = data.get("plan_id")
    if not plan_id:
        return jsonify(ok=False, error="plan_id required"), 400
    from db.queries import get_active_plans, activate_subscription
    plans = {p["id"]: p for p in get_active_plans()}
    plan  = plans.get(int(plan_id))
    if not plan:
        return jsonify(ok=False, error="Invalid or inactive plan"), 400
    if plan["price"] > 0:
        return jsonify(ok=False, error="Payment not yet supported"), 402
    activate_subscription(current_user()["id"], plan["id"], amount_paid=0)
    return jsonify(ok=True)


@app.route("/api/profile", methods=["POST"])
@require_login
def api_profile_save():
    data = request.json or {}
    from db.queries import upsert_user_trading_profile
    upsert_user_trading_profile(
        user_id     = current_user()["id"],
        segment     = data.get("segment", ""),
        risk_type   = data.get("risk_type", ""),
        trader_type = data.get("trader_type", ""),
        focus       = data.get("focus", ""),
        setup_done  = bool(data.get("setup_done", True)),
    )
    return jsonify(ok=True)


# ─────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────

def _preload():
    print("  Loading F&O instrument index from Upstox...", flush=True)
    try:
        from live.fo_instruments import _ensure_loaded
        _ensure_loaded()
        print("  Instrument index ready.", flush=True)
    except Exception as e:
        print(f"  [warning] instrument preload failed: {e}", flush=True)

    try:
        from db.queries import expire_stale_subscriptions
        expire_stale_subscriptions()
        print("  Subscription expiry check done.\n", flush=True)
    except Exception as e:
        print(f"  [warning] subscription expiry check failed: {e}\n", flush=True)


if __name__ == "__main__":
    print(f"\n{'='*52}")
    print("  Drishti  —  Trade Manager")
    print(f"  http://localhost:{PORT}")
    print(f"{'='*52}\n")

    _preload()

    threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)
