#!/usr/bin/env python3
"""
Drishti — Trade Manager Web UI
Run:  python server.py
"""
import sys
import os
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from flask import (Flask, request, jsonify,
                   session, redirect, url_for, abort, g, send_from_directory)
from authlib.integrations.flask_client import OAuth
from flask_cors import CORS

_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edgevest-fe", "dist")

app = Flask(__name__, static_folder=_DIST, static_url_path="/assets")
app.secret_key = os.environ["SECRET_KEY"]

# CORS — allow Vite dev server in dev, nothing extra in prod (same-origin)
_CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _CORS_ORIGINS:
    CORS(app, origins=_CORS_ORIGINS, supports_credentials=True)

# Trust the X-Forwarded-Proto header from nginx so url_for() generates https:// URLs
# and OAuth redirect URIs are correct in prod
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Secure session cookies — enforced in prod (HTTPS), relaxed in dev
_PROD = os.environ.get("FLASK_ENV", "production") != "development"
app.config["SESSION_COOKIE_SECURE"]   = _PROD
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 days


@app.teardown_appcontext
def _close_db(exc):
    db = getattr(g, '_db', None)
    if db is not None:
        db.close()

PORT = int(os.environ.get("PORT", 5555))
# In dev, set FRONTEND_URL=http://localhost:5173 so post-auth redirects go to Vite
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

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
    """For client-role API callers: return 402 if no valid active subscription."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user and user["role"] == "client":
            from db.queries import is_subscription_valid
            if not is_subscription_valid(user["id"]):
                return jsonify(error="No active subscription"), 402
        return f(*args, **kwargs)
    return wrapped

def is_admin(user=None):
    u = user or current_user()
    return u and u["role"] in ("super_admin", "admin")

def is_super_admin(user=None):
    u = user or current_user()
    return u and u["role"] == "super_admin"

def _normalize_legs(legs: list) -> list:
    """Ensure both naming conventions work: type↔instrument_type, expiry↔expiry_str."""
    out = []
    for l in legs:
        leg = dict(l)
        if "type" in leg and "instrument_type" not in leg:
            leg["instrument_type"] = leg["type"]
        if "instrument_type" in leg and "type" not in leg:
            leg["type"] = leg["instrument_type"]
        if "expiry" in leg and "expiry_str" not in leg:
            leg["expiry_str"] = leg["expiry"]
        if "expiry_str" in leg and "expiry" not in leg:
            leg["expiry"] = leg["expiry_str"]
        out.append(leg)
    return out

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
    return redirect(FRONTEND_URL or "/")

@app.route("/auth/google")
def auth_google():
    if FRONTEND_URL:
        redirect_uri = FRONTEND_URL + "/auth/callback"
    else:
        redirect_uri = url_for("auth_callback", _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/auth/callback")
def auth_callback():
    token    = google.authorize_access_token()
    userinfo = token.get("userinfo") or google.userinfo()
    from db.queries import upsert_user
    user = upsert_user(
        google_id = userinfo["sub"],
        email     = userinfo["email"],
        name      = userinfo["name"],
        picture   = userinfo.get("picture", ""),
    )
    if not user["active"]:
        return redirect(FRONTEND_URL or "/")
    session["user"] = user
    if user["role"] == "client":
        from db.queries import expire_stale_subscriptions
        expire_stale_subscriptions()
    return redirect(FRONTEND_URL or "/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(FRONTEND_URL or "/")


# ─────────────────────────────────────────────────────────
# API: current user
# ─────────────────────────────────────────────────────────

@app.route("/api/me")
@require_login
def api_me():
    from db.queries import get_user_by_google_id, get_user_trading_profile, is_subscription_valid
    user = dict(current_user())
    # Verify user still exists in DB (handles deleted-account + stale session)
    db_user = get_user_by_google_id(user.get("google_id", ""))
    if not db_user:
        session.clear()
        return jsonify(error="Unauthorized"), 401
    user    = db_user
    profile = get_user_trading_profile(user["id"])
    user["setup_done"]         = bool(profile and profile.get("setup_done"))
    user["subscription_valid"] = is_subscription_valid(user["id"]) if user.get("role") == "client" else True
    return jsonify(user=user)


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
        if r["instrument_type"] == "EQ":
            label = f"{r['symbol']}  EQ  {r.get('name', '')}"
        elif r["strike"]:
            label = f"{r['symbol']}  {int(r['strike']):,} {r['instrument_type']}  {r['expiry_str']}"
        else:
            label = f"{r['symbol']}  {r['instrument_type']}  {r['expiry_str']}"
        if r["weekly"]:
            label += "  (weekly)"
        if r.get("lot_size") and r["instrument_type"] != "EQ":
            label += f"  · lot {r['lot_size']}"
        results.append({
            "label":           label,
            "symbol":          r["symbol"],
            "instrument_type": r["instrument_type"],
            "instrument_key":  r.get("instrument_key"),
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
        capital    = data.get("capital")
        if user["role"] == "client":
            user_id = user["id"]
        else:
            return jsonify(ok=False, error="Only clients can add accounts"), 403
        if not broker_id:
            return jsonify(ok=False, error="user_id and broker_id are required"), 400
        if not capital or float(capital) <= 0:
            return jsonify(ok=False, error="Initial capital is required"), 400
        try:
            aid = add_account(user_id, broker_id, account_no, label, float(capital))
            return jsonify(ok=True, id=aid)
        except ValueError as e:
            return jsonify(ok=False, error=str(e)), 400
    if user["role"] == "client":
        return jsonify(accounts=get_accounts_for_user(user["id"]))
    return jsonify(accounts=get_accounts())


@app.route("/api/accounts/<int:aid>/capital", methods=["POST"])
@require_login
def api_account_capital(aid):
    from db.queries import get_accounts_for_user, update_account_capital, add_account_capital
    user    = current_user()
    own_ids = {a["id"] for a in get_accounts_for_user(user["id"])}
    if aid not in own_ids:
        return jsonify(ok=False, error="Forbidden"), 403
    data   = request.json or {}
    action = data.get("action", "set")   # "set" or "add"
    amount = data.get("amount")
    if amount is None or float(amount) <= 0:
        return jsonify(ok=False, error="amount must be > 0"), 400
    if action == "add":
        new_cap = add_account_capital(aid, float(amount))
    else:
        update_account_capital(aid, float(amount))
        new_cap = float(amount)
    return jsonify(ok=True, capital=new_cap)


@app.route("/api/accounts/<int:aid>/portfolio")
@require_login
def api_account_portfolio(aid):
    from db.queries import get_accounts_for_user, get_account_portfolio, get_connection
    user    = current_user()
    own_ids = {a["id"] for a in get_accounts_for_user(user["id"])}
    if aid not in own_ids and not is_admin():
        return jsonify(error="Forbidden"), 403
    conn   = get_connection()
    prices = {r["instrument_key"]: r["ltp"]
              for r in conn.execute("SELECT instrument_key, ltp FROM price_cache").fetchall()}
    conn.close()
    pf = get_account_portfolio(aid, prices)
    return jsonify(portfolio=pf)


# ─────────────────────────────────────────────────────────
# API: recommendations
# ─────────────────────────────────────────────────────────

@app.route("/api/recommendations")
@require_login
def api_recommendations():
    from db.queries import get_all_recommendations, get_original_entry_legs, get_current_legs, get_trade_adjustments, get_trade_legs
    recs = get_all_recommendations()
    out  = []
    for r in recs:
        original_legs = get_original_entry_legs(r["id"])
        current_legs  = get_current_legs(r["id"])
        adjustments   = get_trade_adjustments(r["id"])

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

        all_leg_types = {l.get("instrument_type", "") for l in (original_legs + current_legs)}
        if all_leg_types & {"CE", "PE", "FUT"}:
            segment = "F&O"
        elif "ETF" in all_leg_types:
            segment = "ETF"
        elif all_leg_types & {"COMMODITY", "MCX"}:
            segment = "Commodities"
        else:
            segment = "Equity"

        out.append({
            "id":              r["id"],
            "symbol":          r["symbol"],
            "trigger":         r["trigger_name"],
            "status":          r["status"],
            "entry_ist":       _ist_str(r["entry_time"]),
            "exit_ist":        _ist_str(r["exit_time"]) if r.get("exit_time") else None,
            "account_count":   r["account_count"],
            "adj_count":       len(adjustments),
            "segment":         segment,
            "legs":            original_legs,
            "current_legs":    current_legs,
            "exit_legs":       exit_legs,
            "realized_pnl":    realized_pnl,
            "adjustments":     adjustments,
            "margin_required": r.get("margin_required"),
            "margin_final":    r.get("margin_final"),
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
    legs = _normalize_legs(data.get("legs", []))

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
        try:
            from live.manual_trade import recalculate_recommendation_margin
            recalculate_recommendation_margin(rec_id)
        except Exception as e:
            print(f"  [rec adjust margin recalc skipped]  {e}", flush=True)
        return jsonify(ok=True, adjustment_id=adj_id)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


@app.route("/api/recommendations/create", methods=["POST"])
@require_role("super_admin", "admin")
def api_rec_create():
    data   = request.json or {}
    symbol = data.get("symbol", "")
    legs   = _normalize_legs(data.get("legs", []))
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
    from db.queries import (
        get_open_account_trades, get_account_trade_legs,
        get_original_account_entry_legs, get_applied_account_adjustments,
    )
    user       = current_user()
    account_id = request.args.get("account_id", type=int)

    if user["role"] == "client":
        from db.queries import get_accounts_for_user
        all_own   = get_accounts_for_user(user["id"])
        all_ids   = {a["id"] for a in all_own}
        real_ids  = {a["id"] for a in all_own if not a["game_id"]}
        if account_id and account_id in all_ids:
            trades = get_open_account_trades(account_id=account_id)
        else:
            trades = [t for t in get_open_account_trades() if t["account_id"] in real_ids]
    else:
        trades = get_open_account_trades(account_id=account_id)

    from db.queries import get_pending_adjustments_for_account_trade, get_pending_exit_for_account_trade
    out = []
    for t in trades:
        all_at_legs  = get_account_trade_legs(t["id"])
        exited_keys  = {l["instrument_key"] for l in all_at_legs if l["action"] == "exit"}
        current_legs = [l for l in all_at_legs
                        if l["action"] == "entry" and l["instrument_key"] not in exited_keys]
        original_legs = get_original_account_entry_legs(t["id"])
        applied_adjs  = get_applied_account_adjustments(t["id"])
        pending_adjs  = get_pending_adjustments_for_account_trade(t["id"])
        pending_exit  = get_pending_exit_for_account_trade(t["id"])
        out.append({
            "id":                  t["id"],
            "symbol":              t["symbol"] or "—",
            "trigger":             t["trigger_name"],
            "rec_id":              t["recommended_trade_id"],
            "account_id":          t["account_id"],
            "account_label":       t["account_label"] or t["broker_name"] or f"Account {t['account_id']}",
            "trader_name":         t["trader_name"],
            "broker_name":         t["broker_name"],
            "entry_ist":           _ist_str(t["entry_time"]),
            "legs":                original_legs,
            "current_legs":        current_legs,
            "applied_adjustments": applied_adjs,
            "pending_adj_count":   len(pending_adjs),
            "pending_adjustments": pending_adjs,
            "pending_exit":        pending_exit,
            "margin":              t.get("margin"),
        })
    return jsonify(trades=out)


@app.route("/api/account-trades/create", methods=["POST"])
@require_login
def api_account_trade_create():
    data       = request.json or {}
    rec_id     = data.get("recommended_trade_id")
    account_id = data.get("account_id")
    symbol     = data.get("symbol", "")
    legs       = _normalize_legs(data.get("legs", []))
    note       = data.get("note", "")
    user       = current_user()

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
    legs                = _normalize_legs(data.get("legs", []))
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
        try:
            from live.manual_trade import recalculate_account_trade_margin
            recalculate_account_trade_margin(at_id)
        except Exception as me:
            print(f"  [adjust]  margin recalc skipped: {me}", flush=True)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400


@app.route("/api/account-trades/<int:at_id>/exit", methods=["POST"])
@require_login
def api_account_trade_exit(at_id):
    from db.queries import get_open_account_trades, get_accounts_for_user
    data   = request.json or {}
    prices = data.get("prices", [])
    note   = data.get("note", "")
    user   = current_user()

    if is_admin():
        return jsonify(ok=False, error="Admins cannot exit client trades"), 403

    if not prices:
        return jsonify(ok=False, error="prices are required"), 400

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


@app.route("/api/account-trades/<int:at_id>/delete", methods=["POST"])
@require_login
def api_account_trade_delete(at_id):
    from db.queries import get_open_account_trades, get_accounts_for_user, delete_account_trade
    user = current_user()

    if is_admin():
        return jsonify(ok=False, error="Admins cannot delete client trades"), 403

    own_ids = {a["id"] for a in get_accounts_for_user(user["id"])}
    trade   = next((t for t in get_open_account_trades() if t["id"] == at_id), None)
    if not trade or trade["account_id"] not in own_ids:
        return jsonify(ok=False, error="Forbidden — not your trade"), 403

    delete_account_trade(at_id)
    return jsonify(ok=True)


@app.route("/api/recommendations/<int:rec_id>/delete", methods=["POST"])
@require_role("super_admin", "admin")
def api_recommendation_delete(rec_id):
    from db.queries import get_recommendation, delete_recommendation
    rec = get_recommendation(rec_id)
    if not rec:
        return jsonify(ok=False, error="Not found"), 404
    if rec["status"] != "open":
        return jsonify(ok=False, error="Only open recommendations can be deleted"), 400
    try:
        delete_recommendation(rec_id)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True)


@app.route("/api/account-trades/history")
@require_login
def api_account_trades_history():
    from db.queries import get_closed_account_trades
    user       = current_user()
    account_id = request.args.get("account_id", type=int)

    if user["role"] == "client":
        from db.queries import get_accounts_for_user
        all_own   = get_accounts_for_user(user["id"])
        all_ids   = {a["id"] for a in all_own}
        real_ids  = {a["id"] for a in all_own if not a["game_id"]}
        if account_id and account_id in all_ids:
            trades = get_closed_account_trades(account_id=account_id)
        else:
            trades = [t for t in get_closed_account_trades(user_id=user["id"]) if t["account_id"] in real_ids]
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
# API: Games
# ─────────────────────────────────────────────────────────

@app.route("/api/games", methods=["GET"])
@require_login
def api_games_list():
    from db.queries import list_games, entry_count, get_entry
    user = current_user()
    if is_admin():
        games = list_games()
    else:
        games = list_games()
        games = [g for g in games if g["status"] in ("active", "closed", "resolved")]
    uid = user["id"]
    for g in games:
        g["participant_count"] = entry_count(g["id"])
        if not is_admin():
            e = get_entry(g["id"], uid)
            g["my_entry"] = {"rank": e["rank"], "credits_won": e["credits_won"]} if e else None
    return jsonify(games=games)


@app.route("/api/games", methods=["POST"])
@require_role("super_admin", "admin")
def api_games_create():
    from db.queries import create_game, save_game_questions
    d = request.json or {}
    required = ("title", "game_type", "start_time", "end_time")
    for f in required:
        if not d.get(f):
            return jsonify(ok=False, error=f"Missing: {f}"), 400
    gid = create_game(
        title=d["title"], description=d.get("description", ""),
        game_type=d["game_type"], symbol=d.get("symbol"),
        start_time=d["start_time"], end_time=d["end_time"],
        reward_pool=int(d.get("reward_pool") or 0),
        winner_count=int(d.get("winner_count") or 1),
        initial_cash=int(d.get("initial_cash") or 1000000),
        created_by=current_user()["id"],
    )
    if d["game_type"] == "mcq" and d.get("questions"):
        save_game_questions(gid, d["questions"])
    return jsonify(ok=True, id=gid)


@app.route("/api/games/<int:gid>", methods=["GET"])
@require_login
def api_game_detail(gid):
    from db.queries import get_game, get_game_questions, entry_count, get_entry, list_entries
    game = get_game(gid)
    if not game:
        return jsonify(error="Not found"), 404
    game["questions"] = get_game_questions(
        gid, include_answer=is_admin() or game["status"] == "resolved"
    )
    game["participant_count"] = entry_count(gid)
    user = current_user()
    if is_admin():
        game["entries"] = list_entries(gid)
    else:
        e = get_entry(gid, user["id"])
        game["my_entry"] = e
        if game["status"] in ("resolved", "closed"):
            game["entries"] = list_entries(gid)
        elif game["status"] == "active" and e:
            is_prediction = game["game_type"] == "price_prediction"
            rows = []
            for x in list_entries(gid):
                row = {"user_name": x["user_name"], "submitted_at": x["submitted_at"],
                       "user_id": x["user_id"], "rank": None}
                # Price prediction: share predicted value — builds excitement, no unfair advantage
                # MCQ: answers stay hidden until resolution
                if is_prediction and x.get("entry_data"):
                    row["predicted_price"] = x["entry_data"].get("predicted_price")
                rows.append(row)
            game["entries"] = rows

    # For closed leaderboard games, inject live P&L as score so the leaderboard
    # is meaningful before resolve_game() is called
    if game["game_type"] == "leaderboard" and game["status"] == "closed" and game.get("entries"):
        from db.queries import get_game_portfolio
        from db.init_db import get_connection as _gc2
        _c = _gc2()
        _prices = {r["instrument_key"]: r["ltp"]
                   for r in _c.execute("SELECT instrument_key, ltp FROM price_cache").fetchall()}
        _c.close()
        for entry in game["entries"]:
            pf = get_game_portfolio(gid, entry["user_id"], _prices)
            entry["score"] = pf.get("pnl", 0)
        game["entries"].sort(key=lambda x: -(x["score"] or 0))
        for i, entry in enumerate(game["entries"], 1):
            entry["rank"] = i

    return jsonify(game=game)


@app.route("/api/games/<int:gid>", methods=["PUT"])
@require_role("super_admin", "admin")
def api_game_update(gid):
    from db.queries import get_game, update_game, save_game_questions
    game = get_game(gid)
    if not game:
        return jsonify(ok=False, error="Not found"), 404
    if game["status"] not in ("draft", "active"):
        return jsonify(ok=False, error="Cannot edit a closed or resolved game"), 400
    d = request.json or {}
    update_game(gid, **{k: d[k] for k in
        ("title","description","symbol","start_time","end_time",
         "reward_pool","winner_count","initial_cash") if k in d})
    if d.get("questions") is not None:
        save_game_questions(gid, d["questions"])
    return jsonify(ok=True)


@app.route("/api/games/<int:gid>/activate", methods=["POST"])
@require_role("super_admin", "admin")
def api_game_activate(gid):
    from db.queries import get_game, set_game_status
    game = get_game(gid)
    if not game:
        return jsonify(ok=False, error="Not found"), 404
    if game["status"] != "draft":
        return jsonify(ok=False, error="Only draft games can be activated"), 400
    set_game_status(gid, "active")
    return jsonify(ok=True)


@app.route("/api/games/<int:gid>/close", methods=["POST"])
@require_role("super_admin", "admin")
def api_game_close(gid):
    from db.queries import get_game, set_game_status, get_open_account_trades
    from db.init_db import get_connection as _gc
    game = get_game(gid)
    if not game:
        return jsonify(ok=False, error="Not found"), 404
    if game["status"] != "active":
        return jsonify(ok=False, error="Only active games can be closed"), 400

    set_game_status(gid, "closed")

    # Deactivate game accounts and auto-exit all open trades at current LTP
    conn = _gc()
    game_account_ids = [
        r[0] for r in conn.execute(
            "SELECT id FROM accounts WHERE game_id = ?", (gid,)
        ).fetchall()
    ]
    if game_account_ids:
        conn.execute(
            f"UPDATE accounts SET active=0 WHERE game_id=?", (gid,)
        )
        conn.commit()
    conn.close()

    # Load price cache once for all trades
    pc_conn = _gc()
    prices_map = {r[0]: r[1] for r in pc_conn.execute(
        "SELECT instrument_key, ltp FROM price_cache"
    ).fetchall()}
    pc_conn.close()

    from db.queries import get_account_trade_legs
    from live.manual_trade import close_account_trade

    exited, failed = [], []
    for acct_id in game_account_ids:
        open_trades = get_open_account_trades(account_id=acct_id)
        for trade in open_trades:
            at_id = trade["id"]
            try:
                entry_legs = [l for l in get_account_trade_legs(at_id) if l["action"] == "entry"]
                prices = [prices_map.get(l["instrument_key"], l["price"] or 0) for l in entry_legs]
                close_account_trade(at_id, prices, note="Game closed — auto-exited at LTP")
                exited.append(at_id)
            except Exception as e:
                print(f"  [game_close]  auto-exit at_id={at_id} failed: {e}", flush=True)
                failed.append({"trade_id": at_id, "error": str(e)})

    return jsonify(ok=True, exited=exited, failed=failed)


@app.route("/api/games/<int:gid>/resolve", methods=["POST"])
@require_role("super_admin", "admin")
def api_game_resolve(gid):
    from db.queries import get_game, resolve_game
    game = get_game(gid)
    if not game:
        return jsonify(ok=False, error="Not found"), 404
    if game["status"] != "closed":
        return jsonify(ok=False, error="Close the game before resolving"), 400
    d = request.json or {}
    try:
        winners = resolve_game(gid, result_value=d.get("result_value"))
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    # Ensure game accounts are deactivated (safety net if close step missed it)
    from db.init_db import get_connection as _gc
    _conn = _gc()
    _conn.execute("UPDATE accounts SET active=0 WHERE game_id=?", (gid,))
    _conn.commit()
    _conn.close()

    return jsonify(ok=True, winners=winners)


@app.route("/api/games/<int:gid>/delete", methods=["POST"])
@require_role("super_admin", "admin")
def api_game_delete(gid):
    from db.queries import delete_game
    try:
        delete_game(gid)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True)


@app.route("/api/games/<int:gid>/enter", methods=["POST"])
@require_login
def api_game_enter(gid):
    from db.queries import get_game, submit_entry, create_game_virtual_account
    if is_admin():
        return jsonify(ok=False, error="Admins cannot enter games"), 403
    game = get_game(gid)
    if not game:
        return jsonify(ok=False, error="Not found"), 404
    if game["status"] != "active":
        return jsonify(ok=False, error="Game is not accepting entries"), 400
    d = request.json or {}
    entry_data = d.get("entry_data", {})
    uid = current_user()["id"]
    eid = submit_entry(gid, uid, entry_data)
    if game["game_type"] == "leaderboard":
        create_game_virtual_account(gid, uid, f"🎮 {game['title']}", game["initial_cash"])
    return jsonify(ok=True, entry_id=eid)


@app.route("/api/games/<int:gid>/leaderboard", methods=["GET"])
@require_login
def api_game_leaderboard(gid):
    from db.queries import get_game, list_entries
    game = get_game(gid)
    if not game:
        return jsonify(error="Not found"), 404
    if game["status"] not in ("closed", "resolved") and not is_admin():
        return jsonify(error="Leaderboard not available yet"), 403
    entries = list_entries(gid)
    return jsonify(entries=entries)


@app.route("/api/games/<int:gid>/trade", methods=["POST"])
@require_login
def api_game_trade(gid):
    from db.queries import get_game, add_virtual_trade, submit_entry, get_entry
    if is_admin():
        return jsonify(ok=False, error="Admins cannot trade in games"), 403
    game = get_game(gid)
    if not game or game["game_type"] != "leaderboard":
        return jsonify(ok=False, error="Not a leaderboard game"), 400
    d = request.json or {}
    uid = current_user()["id"]
    if not get_entry(gid, uid):
        submit_entry(gid, uid, {})
    try:
        add_virtual_trade(gid, uid,
                          symbol=d["symbol"], action=d["action"],
                          price=float(d["price"]), quantity=int(d["quantity"]))
    except (ValueError, KeyError) as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True)


@app.route("/api/games/<int:gid>/portfolio", methods=["GET"])
@require_login
def api_game_portfolio(gid):
    from db.queries import get_game, get_game_portfolio, get_connection
    game = get_game(gid)
    if not game or game["game_type"] != "leaderboard":
        return jsonify(error="Not a leaderboard game"), 400
    conn   = get_connection()
    prices = {r["instrument_key"]: r["ltp"]
              for r in conn.execute("SELECT instrument_key, ltp FROM price_cache").fetchall()}
    conn.close()
    uid = current_user()["id"]
    pf  = get_game_portfolio(gid, uid, prices)
    return jsonify(portfolio=pf)


# ─────────────────────────────────────────────────────────
# API: Credits
# ─────────────────────────────────────────────────────────

@app.route("/api/credits", methods=["GET"])
@require_login
def api_credits():
    from db.queries import get_user_credits, get_credit_history
    uid = current_user()["id"]
    return jsonify(
        balance=get_user_credits(uid),
        history=get_credit_history(uid),
    )


# ─────────────────────────────────────────────────────────
# API: prices / spot
# ─────────────────────────────────────────────────────────

def _spot_data() -> dict:
    from config import SPOT_IKEYS, SPOT_DISPLAY
    from db.queries import get_cached_spot
    display_ikeys = [SPOT_IKEYS[s] for s in SPOT_DISPLAY if s in SPOT_IKEYS]
    ikey_to_sym   = {SPOT_IKEYS[s]: s for s in SPOT_DISPLAY if s in SPOT_IKEYS}
    spot, _       = get_cached_spot(display_ikeys)
    out = {}
    for ikey in display_ikeys:
        if ikey not in spot:
            continue
        d   = spot[ikey]
        ltp = d["ltp"]
        pc  = d["prev_close"]
        out[ikey_to_sym[ikey]] = {"ltp": ltp, "change": round(ltp - pc, 2) if pc else None}
    return out


@app.route("/api/prices", methods=["POST"])
@require_login
def api_prices():
    from db.queries import get_cached_prices
    keys = (request.json or {}).get("keys", [])
    prices, ts = get_cached_prices(keys) if keys else ({}, None)
    prices["_spot"] = _spot_data()
    if ts:
        prices["_ts"] = ts
    return jsonify(prices)


@app.route("/api/spot")
@require_login
def api_spot():
    return jsonify(_spot_data())


# ─────────────────────────────────────────────────────────
# edgevest-fe — serve React build for all non-API routes
# ─────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react(path):
    full = os.path.join(_DIST, path)
    if path and os.path.exists(full):
        return send_from_directory(_DIST, path)
    return send_from_directory(_DIST, "index.html")


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


@app.route("/api/subscribe-with-credits", methods=["POST"])
@require_login
def api_subscribe_with_credits():
    data    = request.json or {}
    plan_id = data.get("plan_id")
    if not plan_id:
        return jsonify(ok=False, error="plan_id required"), 400
    from db.queries import subscribe_with_credits
    result = subscribe_with_credits(current_user()["id"], int(plan_id))
    return jsonify(result), (200 if result["ok"] else 400)


@app.route("/api/profile", methods=["GET", "POST"])
@require_login
def api_profile_save():
    from db.queries import get_user_trading_profile, upsert_user_trading_profile
    uid = current_user()["id"]
    if request.method == "GET":
        profile = get_user_trading_profile(uid) or {}
        return jsonify(profile=profile)
    data = request.json or {}
    print(f"[api/profile] POST uid={uid} data={data}", flush=True)
    upsert_user_trading_profile(
        user_id     = uid,
        segment     = data.get("segment", ""),
        risk_type   = data.get("risk_type", ""),
        trader_type = data.get("trader_type", ""),
        focus       = data.get("focus", ""),
        setup_done  = bool(data.get("setup_done", True)),
    )
    profile = get_user_trading_profile(uid)
    print(f"[api/profile] saved → {profile}", flush=True)
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

    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)
