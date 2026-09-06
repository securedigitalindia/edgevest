# Manual Strategy CLI — hand-author multi-leg recommended_trades from a
# terminal, with a draft -> publish workflow plus adjust/exit on published
# trades. Admin-only tool; never imported by server.py/the Flask app.
#
# Spec: docs/prd/manual-strategy-cli.md
#
# ============================================================
#  Usage:
#    python strategy_cli.py create --symbol NIFTY50 --note "..." \
#        --leg "side=SELL,type=PE,strike=24000,expiry=May 2026,lots=2,price_mode=limit,price=150.5" \
#        --leg "side=BUY,type=PE,strike=23500,expiry=May 2026,lots=2,price_mode=market"
#    python strategy_cli.py add-leg <trade_id> --leg "..."
#    python strategy_cli.py show <trade_id>
#    python strategy_cli.py list-drafts [--symbol NIFTY50]
#    python strategy_cli.py publish <trade_id>
#    python strategy_cli.py discard <trade_id>
#    python strategy_cli.py adjust <trade_id> --type add_legs --leg "..." [--note "..."]
#    python strategy_cli.py exit <trade_id> --leg "type=PE,strike=24000,expiry=May 2026,price_mode=market" [--note "..."]
#
#  Leg spec (--leg, repeatable), comma-separated key=value:
#    side=BUY|SELL            required for create/add-leg/adjust legs
#    type=PE|CE|FUT|EQ        required always
#    strike=<int>             required for PE/CE
#    expiry="May 2026"        required for PE/CE/FUT ("D Mon YYYY" or "Mon YYYY")
#    instrument_key=<key>     required for EQ (instead of strike/expiry)
#    lots=<int>               required for create/add-leg/adjust legs
#    price_mode=market|limit  required always
#    price=<float>            required iff price_mode=limit, rejected iff market
#
#  `exit` legs omit side/lots — they're matched to the trade's current legs
#  by identity (type/strike/expiry, or instrument_key for EQ), not position.
#
#  Shorthand leg spec (--legs, repeatable), a compact alternative to --leg
#  for PE/CE/FUT legs — one comma-separated token per leg, '&'-joined for
#  multiple legs in a single flag:
#    SIDE,MODE,STRIKE+TYPE,LOTS,EXPIRY
#      SIDE       B|S              -> BUY|SELL
#      MODE       M                -> price_mode=market
#                 L<price>         -> price_mode=limit, e.g. L1548.17
#      STRIKE+TYPE  <strike>CE|PE  e.g. 24000CE   (or bare FUT, no strike)
#      LOTS       <int>
#      EXPIRY     8sep2026 | 8 Sep 2026 | May 2026
#    e.g. --legs "B,M,24000CE,1,8sep2026"
#         --legs "B,M,24000CE,1,8sep2026&S,M,24300CE,2,8sep2026"
#    Not supported for EQ legs (no instrument_key field) — use --leg instead.
#    `exit` accepts the same shorthand; SIDE/LOTS are parsed but ignored
#    there since exit legs are matched to current legs by strike+type/expiry,
#    not by side. --leg and --legs may be mixed freely on the same command.
# ============================================================

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Same env-loading as server.py — FRONTEND_URL (and anything else in
# backend/.env.<FLASK_ENV>) needs to be loaded here too now that Telegram
# alerts fired from this standalone CLI (publish/adjust/exit) build a link
# back into the frontend (live/alert.py's _frontend_url()). FLASK_ENV must
# still be set explicitly — no smart default, matches server.py's own
# behavior — defaults to production if unset.
from dotenv import load_dotenv
load_dotenv(f".env.{os.environ.get('FLASK_ENV', 'production')}")

from db.queries import (
    open_recommended_trade, add_trade_legs, get_recommendation, get_current_legs,
    get_trade_adjustments, delete_recommendation,
    list_recommendations_by_status, add_trade_adjustment, close_recommended_trade,
    get_cached_prices,
)
from live.fo_instruments import fo_ikey, fo_lot_size, resolve_expiry, SPOT_IKEYS
from live.manual_trade import (
    recalculate_recommendation_margin, auto_exit_linked_account_trades,
    publish_manual_trade,
)
from live.alert import send_adjustment_alert, send_rec_exit_alert

IST = ZoneInfo("Asia/Kolkata")

# Mirrors server.py's RISK_LEVELS — duplicated rather than imported so this
# standalone script never triggers Flask app / OAuth / CORS setup just to
# read a constant.
_RISK_LEVELS = {"low", "mid", "high", "very_high"}

_ADJ_TYPES = ("add_legs", "replace_legs", "partial_exit")


class CLIError(Exception):
    """Any user-facing error — caught in main(), printed without a traceback."""


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ist(utc_str: str | None) -> str:
    if not utc_str:
        return "—"
    try:
        dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).strftime("%d %b %Y  %H:%M IST")
    except ValueError:
        return utc_str


def _require_trade(trade_id: int) -> dict:
    trade = get_recommendation(trade_id)
    if not trade:
        raise CLIError(f"trade {trade_id} not found")
    return trade


def _spot_snapshot(symbol: str) -> float:
    """Informational spot snapshot only (entry_ltp display field) — read from
    the shared price_cache, same mechanism manual_trade.py uses. Soft-fails
    to 0.0 (never blocks a command), unlike leg prices which hard-error."""
    spot_ikey = SPOT_IKEYS.get(symbol)
    if not spot_ikey:
        return 0.0
    try:
        cached, _ = get_cached_prices([spot_ikey])
        return cached.get(spot_ikey, 0.0)
    except Exception as e:
        print(f"  [strategy_cli]  spot fetch failed: {e}", flush=True)
        return 0.0


def _fetch_market_price(ikey: str | None) -> float:
    """Live LTP via the same direct-API primitive triggers.py's
    Nifty500MultipleTrigger._fetch_prices() uses — NOT price_cache. Aborts
    with a clear error rather than ever recording None/zero silently."""
    if not ikey:
        raise CLIError("price_mode=market requires a resolved instrument_key")
    from live.upstox_client import get_ltp
    try:
        prices = get_ltp([ikey])
    except Exception as e:
        raise CLIError(f"live price fetch failed for {ikey}: {e}")
    price = prices.get(ikey)
    if not price:
        raise CLIError(f"no live price returned for {ikey}")
    return price


def _print_legs(legs: list[dict], indent: int = 2):
    pad = " " * indent
    if not legs:
        print(f"{pad}(none)")
        return
    for l in legs:
        strike_str = f"{int(l['strike']):,} " if l.get("strike") else ""
        expiry_str = f"  {l['expiry_str']}" if l.get("expiry_str") else ""
        price = l.get("price")
        price_str = f"@₹{price:,.2f}" if price is not None else "@—"
        print(f"{pad}{l['side']:<4}  {strike_str}{l['instrument_type']}{expiry_str}"
              f"  {l.get('lots', 1)}L  {price_str}")


# ---------------------------------------------------------------------------
# Leg parsing / resolution — entry-style legs (create / add-leg / adjust)
# ---------------------------------------------------------------------------

def _parse_leg_spec(spec: str) -> dict:
    """'key=value,key=value,...' -> {key: value} (raw strings, lowercased keys)."""
    out = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise CLIError(f"invalid --leg segment {part!r} — expected key=value")
        k, v = part.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


_SHORTHAND_SIDE = {"b": "BUY", "s": "SELL"}
_SHORTHAND_STRIKE_TYPE = re.compile(r"^(\d+)(CE|PE)$", re.IGNORECASE)


def _normalize_shorthand_expiry(tok: str) -> str:
    """'8sep2026' -> '8 Sep 2026', 'sep2026' -> 'Sep 2026'; anything already
    spaced (or otherwise shaped) passes through unchanged for resolve_expiry
    to validate/reject itself."""
    tok = tok.strip()
    m = re.match(r"^(\d{1,2})([A-Za-z]{3,})(\d{4})$", tok)
    if m:
        day, mon, year = m.groups()
        return f"{day} {mon.capitalize()} {year}"
    m = re.match(r"^([A-Za-z]{3,})(\d{4})$", tok)
    if m:
        mon, year = m.groups()
        return f"{mon.capitalize()} {year}"
    return tok


def _parse_shorthand_leg(token: str) -> str:
    """'B,M,24000CE,1,8sep2026' / 'S,L1548.17,24000PE,2,8sep2026' / 'B,M,FUT,1,8sep2026'
    -> the equivalent key=value leg-spec string consumed by _parse_leg_spec().
    PE/CE/FUT only — EQ legs (no strike, need instrument_key) use --leg."""
    parts = [p.strip() for p in token.split(",")]
    if len(parts) != 5:
        raise CLIError(f"shorthand leg {token!r} must have 5 comma-separated fields: "
                        f"SIDE,MODE,STRIKE+TYPE,LOTS,EXPIRY")
    side_raw, mode_raw, st_raw, lots_raw, expiry_raw = parts

    side = _SHORTHAND_SIDE.get(side_raw.lower())
    if not side:
        raise CLIError(f"shorthand side must be B or S, got {side_raw!r}")

    if mode_raw.upper() == "M":
        mode_kv = "price_mode=market"
    elif mode_raw[:1].upper() == "L" and mode_raw[1:]:
        mode_kv = f"price_mode=limit,price={mode_raw[1:]}"
    else:
        raise CLIError(f"shorthand mode must be 'M' or 'L<price>' (e.g. L1548.17), got {mode_raw!r}")

    st = st_raw.strip().upper()
    if st == "FUT":
        type_kv = "type=FUT"
    else:
        m = _SHORTHAND_STRIKE_TYPE.match(st)
        if not m:
            raise CLIError(f"shorthand strike+type must be like '24000CE' or 'FUT', got {st_raw!r}")
        strike, opt = m.groups()
        type_kv = f"type={opt.upper()},strike={strike}"

    try:
        lots = int(lots_raw)
    except ValueError:
        raise CLIError(f"shorthand lots must be an integer, got {lots_raw!r}")

    expiry = _normalize_shorthand_expiry(expiry_raw)
    return f"side={side},{mode_kv},{type_kv},lots={lots},expiry={expiry}"


def _expand_legs(leg_args: list[str] | None, legs_shorthand: list[str] | None) -> list[str]:
    """Merge --leg (full key=value form) and --legs (compact shorthand,
    '&'-joined per flag, repeatable) into one flat list of key=value leg
    specs — the rest of the pipeline (_parse_leg_spec onward) never knows
    which form a leg came from."""
    out = list(leg_args or [])
    for group in (legs_shorthand or []):
        for token in group.split("&"):
            token = token.strip()
            if token:
                out.append(_parse_shorthand_leg(token))
    return out


def _resolve_entry_leg(symbol: str, raw: dict, now_utc: str) -> dict:
    """
    Resolve one --leg spec into the trade_legs row shape used by
    add_trade_legs()/add_trade_adjustment() — side/type/lots/price_mode
    required; strike/expiry required for PE/CE(/FUT for expiry only);
    instrument_key required for EQ. Instrument resolution (instrument_key,
    lot_size, expiry parsing) reuses fo_ikey()/fo_lot_size()/resolve_expiry()
    exactly as manual_trade.py's _resolve_legs() does.
    """
    required = {"side", "type", "lots", "price_mode"}
    missing = required - raw.keys()
    if missing:
        raise CLIError(f"leg missing required field(s) {sorted(missing)} — got {raw}")

    side = raw["side"].upper()
    if side not in ("BUY", "SELL"):
        raise CLIError(f"leg side must be BUY or SELL, got {raw['side']!r}")

    itype = raw["type"].upper()
    if itype not in ("PE", "CE", "FUT", "EQ"):
        raise CLIError(f"leg type must be PE/CE/FUT/EQ, got {raw['type']!r}")

    try:
        lots = int(raw["lots"])
    except ValueError:
        raise CLIError(f"leg lots must be an integer, got {raw['lots']!r}")
    if lots <= 0:
        raise CLIError(f"leg lots must be positive, got {lots}")

    price_mode = raw["price_mode"].lower()
    if price_mode not in ("market", "limit"):
        raise CLIError(f"leg price_mode must be 'market' or 'limit', got {raw['price_mode']!r}")
    if price_mode == "limit" and "price" not in raw:
        raise CLIError("leg price_mode=limit requires 'price'")
    if price_mode == "market" and "price" in raw:
        raise CLIError("leg price_mode=market must not include 'price'")

    expiry_date = None
    expiry_str  = None
    strike      = None
    ikey        = None
    lot_sz      = 0

    if itype in ("PE", "CE", "FUT"):
        expiry_raw = raw.get("expiry")
        if not expiry_raw:
            raise CLIError(f"leg type={itype} requires 'expiry'")
        expiry_date = resolve_expiry(symbol, expiry_raw)
        if expiry_date is None:
            raise CLIError(f"could not resolve expiry {expiry_raw!r} for {symbol}")
        expiry_str = expiry_date.strftime("%d %b %Y")

        if itype in ("PE", "CE"):
            if "strike" not in raw:
                raise CLIError(f"leg type={itype} requires 'strike'")
            try:
                strike = int(raw["strike"])
            except ValueError:
                raise CLIError(f"leg strike must be an integer, got {raw['strike']!r}")

        _strike = strike if itype in ("PE", "CE") else 0
        ikey = fo_ikey(symbol, itype, expiry_date, strike=_strike or 0)
        if ikey is None:
            ikey = fo_ikey(symbol, itype, expiry_date, strike=_strike or 0, weekly=True)
        if ikey is None:
            raise CLIError(f"could not resolve instrument for {symbol} {itype} "
                            f"{strike or ''} {expiry_str}".strip())
        lot_sz = fo_lot_size(symbol, expiry_date) or 0

    elif itype == "EQ":
        ikey = raw.get("instrument_key")
        if not ikey:
            raise CLIError("leg type=EQ requires 'instrument_key'")
        lot_sz = int(raw.get("lot_size") or 1)

    if price_mode == "limit":
        try:
            price = float(raw["price"])
        except ValueError:
            raise CLIError(f"leg price must be a number, got {raw['price']!r}")
    else:
        price = _fetch_market_price(ikey)

    return {
        "action":          "entry",
        "side":            side,
        "instrument_type": itype,
        "instrument_key":  ikey,
        "strike":          strike,
        "expiry_str":      expiry_str,
        "lots":            lots,
        "lot_size":        lot_sz,
        "price":           price,
        "ts":              now_utc,
    }


def _resolve_entry_legs(symbol: str, specs: list[str], now_utc: str) -> list[dict]:
    if not specs:
        raise CLIError("at least one --leg or --legs is required")
    return [_resolve_entry_leg(symbol, _parse_leg_spec(s), now_utc) for s in specs]


# ---------------------------------------------------------------------------
# Leg parsing / matching — exit-style legs (self-identifying, not positional)
# ---------------------------------------------------------------------------

def _leg_identity(leg: dict) -> tuple:
    if leg["instrument_type"] == "EQ":
        return ("EQ_IKEY", leg["instrument_key"])
    strike = int(leg["strike"]) if leg.get("strike") else None
    return ("TYPED", leg["instrument_type"], strike, leg.get("expiry_str"))


def _parse_exit_leg_spec(symbol: str, raw: dict) -> dict:
    """Returns {'identity', 'price_mode', 'price_raw'} — identity matches
    _leg_identity() of a current leg, exactly, no positional info."""
    itype = raw.get("type", "").upper()
    if itype not in ("PE", "CE", "FUT", "EQ"):
        raise CLIError(f"leg type must be PE/CE/FUT/EQ, got {raw.get('type')!r}")

    if "price_mode" not in raw:
        raise CLIError("leg requires 'price_mode' (market|limit)")
    price_mode = raw["price_mode"].lower()
    if price_mode not in ("market", "limit"):
        raise CLIError(f"leg price_mode must be 'market' or 'limit', got {raw['price_mode']!r}")
    if price_mode == "limit" and "price" not in raw:
        raise CLIError("leg price_mode=limit requires 'price'")
    if price_mode == "market" and "price" in raw:
        raise CLIError("leg price_mode=market must not include 'price'")

    if itype == "EQ":
        ikey = raw.get("instrument_key")
        if not ikey:
            raise CLIError("leg type=EQ requires 'instrument_key'")
        identity = ("EQ_IKEY", ikey)
    else:
        expiry_raw = raw.get("expiry")
        if not expiry_raw:
            raise CLIError(f"leg type={itype} requires 'expiry'")
        expiry_date = resolve_expiry(symbol, expiry_raw)
        if expiry_date is None:
            raise CLIError(f"could not resolve expiry {expiry_raw!r} for {symbol}")
        expiry_str = expiry_date.strftime("%d %b %Y")

        strike = None
        if itype in ("PE", "CE"):
            if "strike" not in raw:
                raise CLIError(f"leg type={itype} requires 'strike'")
            try:
                strike = int(raw["strike"])
            except ValueError:
                raise CLIError(f"leg strike must be an integer, got {raw['strike']!r}")
        identity = ("TYPED", itype, strike, expiry_str)

    return {"identity": identity, "price_mode": price_mode, "price_raw": raw.get("price")}


def _match_exit_legs(current_legs: list[dict], parsed_specs: list[dict]) -> list[tuple[dict, dict]]:
    """
    Match every --leg spec to exactly one current leg by identity. Every
    current leg must be matched exactly once, or this errors out before any
    price is fetched / anything is written.
    """
    remaining = list(current_legs)
    matched: list[tuple[dict, dict]] = []
    for spec in parsed_specs:
        candidates = [l for l in remaining if _leg_identity(l) == spec["identity"]]
        if not candidates:
            raise CLIError(f"no current leg matches --leg identity {spec['identity']}")
        if len(candidates) > 1:
            # get_current_legs() nets per instrument_key, so this shouldn't
            # be reachable — guarded defensively anyway.
            raise CLIError(f"ambiguous match for --leg identity {spec['identity']}")
        leg = candidates[0]
        remaining.remove(leg)
        matched.append((leg, spec))
    if remaining:
        missing = ", ".join(str(_leg_identity(l)) for l in remaining)
        raise CLIError(f"missing --leg for current position(s): {missing}")
    return matched


def _resolve_exit_price(spec: dict, ikey: str | None) -> float:
    if spec["price_mode"] == "limit":
        try:
            return float(spec["price_raw"])
        except (TypeError, ValueError):
            raise CLIError(f"leg price must be a number, got {spec['price_raw']!r}")
    return _fetch_market_price(ikey)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_create(args):
    symbol = args.symbol.upper()
    if args.risk_level and args.risk_level not in _RISK_LEVELS:
        raise CLIError(f"--risk-level must be one of {sorted(_RISK_LEVELS)}")

    now_utc = _now_utc()
    resolved_legs = _resolve_entry_legs(symbol, _expand_legs(args.leg, args.legs), now_utc)
    spot_ltp = _spot_snapshot(symbol)

    trade_id = open_recommended_trade(
        trigger_name    = "MANUAL_CLI",
        symbol          = symbol,
        entry_level     = 0,
        entry_ltp       = spot_ltp,
        entry_time      = now_utc,
        exit_level      = 0,
        expiry_strs     = [l.get("expiry_str") for l in resolved_legs],
        note            = args.note or None,
        risk_level      = args.risk_level or None,
        status          = "draft",
    )
    add_trade_legs(trade_id, resolved_legs)

    print(f"Draft created: trade_id={trade_id}  {symbol}  {len(resolved_legs)} leg(s)")
    _print_legs(resolved_legs)
    print("Status: draft — invisible to clients, no Telegram alert sent.")
    print(f"Run 'python strategy_cli.py publish {trade_id}' when ready.")


def cmd_add_leg(args):
    trade = _require_trade(args.trade_id)
    if trade["status"] != "draft":
        raise CLIError(f"trade {args.trade_id} is '{trade['status']}' — add-leg only works on a draft")

    now_utc = _now_utc()
    resolved_legs = _resolve_entry_legs(trade["symbol"], _expand_legs(args.leg, args.legs), now_utc)
    add_trade_legs(args.trade_id, resolved_legs)

    print(f"Added {len(resolved_legs)} leg(s) to draft trade_id={args.trade_id}")
    _print_legs(resolved_legs)


def cmd_show(args):
    trade = _require_trade(args.trade_id)
    legs  = get_current_legs(args.trade_id)
    adjustments = get_trade_adjustments(args.trade_id)

    print(f"Trade #{trade['id']}  {trade['symbol']}  status={trade['status']}  "
          f"trigger={trade['trigger_name']}  display_code={trade.get('display_code')}")
    print(f"  entry_time      : {_ist(trade['entry_time'])}")
    if trade.get("exit_time"):
        print(f"  exit_time       : {_ist(trade['exit_time'])}")
    print(f"  entry_ltp       : {trade.get('entry_ltp')}")
    if trade.get("exit_ltp") is not None:
        print(f"  exit_ltp        : {trade.get('exit_ltp')}")
    print(f"  margin_required : {trade.get('margin_required')}")
    print(f"  margin_final    : {trade.get('margin_final')}")
    if trade.get("risk_level"):
        print(f"  risk_level      : {trade['risk_level']}")
    if trade.get("note"):
        print(f"  note            : {trade['note']}")

    print(f"  current legs ({len(legs)}):")
    _print_legs(legs)

    if adjustments:
        print(f"  adjustments ({len(adjustments)}):")
        for adj in adjustments:
            print(f"    #{adj['id']}  {adj['adj_type']}  {_ist(adj['ts'])}  {adj.get('note') or ''}")
            _print_legs(adj["legs"], indent=6)


def cmd_list_drafts(args):
    drafts = list_recommendations_by_status("draft")
    if args.symbol:
        drafts = [d for d in drafts if d["symbol"] == args.symbol.upper()]

    if not drafts:
        print("No draft trades.")
        return

    for d in drafts:
        legs = get_current_legs(d["id"])
        print(f"#{d['id']:<5} {d['symbol']:<10} {len(legs)} leg(s)  "
              f"created {_ist(d['entry_time'])}"
              + (f"  note={d['note']}" if d.get("note") else ""))


def cmd_publish(args):
    try:
        updated = publish_manual_trade(args.trade_id)
    except ValueError as e:
        raise CLIError(str(e))

    print(f"Published trade_id={args.trade_id}  {updated['symbol']}  status=open")
    print(f"  entry_time   : {_ist(updated['entry_time'])}")
    print(f"  entry_ltp    : {updated.get('entry_ltp')}")
    print(f"  margin_final : {updated.get('margin_final')}")
    print("  Telegram alert sent.")


def cmd_discard(args):
    trade = _require_trade(args.trade_id)
    if trade["status"] != "draft":
        raise CLIError(f"trade {args.trade_id} is '{trade['status']}' — discard only works on a draft")

    delete_recommendation(args.trade_id)
    print(f"Draft trade_id={args.trade_id} discarded — row and legs removed.")


def cmd_adjust(args):
    trade = _require_trade(args.trade_id)
    if trade["status"] != "open":
        raise CLIError(f"trade {args.trade_id} is '{trade['status']}' — adjust only works on an open trade")
    if args.type not in _ADJ_TYPES:
        raise CLIError(f"--type must be one of {_ADJ_TYPES}")

    now_utc = _now_utc()
    resolved_legs = _resolve_entry_legs(trade["symbol"], _expand_legs(args.leg, args.legs), now_utc)

    adj_id = add_trade_adjustment(args.trade_id, args.type, args.note or None, now_utc, resolved_legs)
    recalculate_recommendation_margin(args.trade_id)
    send_adjustment_alert(args.trade_id, trade["symbol"], trade.get("display_code"), args.type, resolved_legs, args.note or "")

    print(f"Adjustment #{adj_id} ({args.type}) recorded on trade_id={args.trade_id}")
    _print_legs(resolved_legs)
    print("  Telegram alert sent.")


def cmd_exit(args):
    trade = _require_trade(args.trade_id)
    if trade["status"] != "open":
        raise CLIError(f"trade {args.trade_id} is '{trade['status']}' — exit only works on an open trade")

    current_legs = get_current_legs(args.trade_id)
    if not current_legs:
        raise CLIError(f"trade {args.trade_id} has no current legs to exit")

    leg_specs = _expand_legs(args.leg, args.legs)
    if not leg_specs:
        raise CLIError("exit requires one --leg/--legs entry per current leg")

    parsed_specs = [_parse_exit_leg_spec(trade["symbol"], _parse_leg_spec(s)) for s in leg_specs]
    matched = _match_exit_legs(current_legs, parsed_specs)

    now_utc = _now_utc()
    exit_legs = []
    exit_info = []
    for leg, spec in matched:
        price = _resolve_exit_price(spec, leg["instrument_key"])
        exit_legs.append({
            "action":          "exit",
            "side":            "BUY" if leg["side"] == "SELL" else "SELL",
            "instrument_type": leg["instrument_type"],
            "instrument_key":  leg["instrument_key"],
            "strike":          leg["strike"],
            "expiry_str":      leg["expiry_str"],
            "lots":            leg["lots"],
            "lot_size":        leg["lot_size"],
            "price":           price,
            "ts":              now_utc,
        })
        exit_info.append({**leg, "price": price})

    # Mirrors server.py's /api/recommendations/<id>/exit exactly, including
    # this exit_ltp derivation, so DB/Telegram effects match the HTTP route.
    exit_ltp = exit_legs[0]["price"] if exit_legs else trade["entry_ltp"]

    close_recommended_trade(args.trade_id, exit_ltp, now_utc, exit_legs=exit_legs)
    send_rec_exit_alert(args.trade_id, trade["symbol"], trade.get("display_code"), exit_info)
    try:
        auto_exit_linked_account_trades(args.trade_id, exit_legs, now_utc)
    except Exception as e:
        print(f"  [strategy_cli]  auto-exit linked account trades failed: {e}", flush=True)

    print(f"Trade_id={args.trade_id} fully exited.  exit_ltp={exit_ltp}")
    _print_legs(exit_legs)
    print("  Telegram alert sent.")


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="strategy_cli.py",
        description="Hand-author multi-leg recommended_trades: draft, publish, adjust, exit. Admin-only.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Start a new draft strategy")
    p_create.add_argument("--symbol", required=True)
    p_create.add_argument("--note", default="")
    p_create.add_argument("--risk-level", dest="risk_level", default=None)
    p_create.add_argument("--leg", action="append", default=[],
                           help="side=...,type=...,strike=...,expiry=...,lots=...,price_mode=...,price=...")
    p_create.add_argument("--legs", action="append", default=[],
                           help="shorthand, '&'-joined: SIDE,MODE,STRIKE+TYPE,LOTS,EXPIRY "
                                "e.g. 'B,M,24000CE,1,8sep2026&S,M,24300CE,2,8sep2026'")
    p_create.set_defaults(func=cmd_create)

    p_add_leg = sub.add_parser("add-leg", help="Add leg(s) to a still-draft trade")
    p_add_leg.add_argument("trade_id", type=int)
    p_add_leg.add_argument("--leg", action="append", default=[])
    p_add_leg.add_argument("--legs", action="append", default=[],
                            help="shorthand, see 'create --legs'")
    p_add_leg.set_defaults(func=cmd_add_leg)

    p_show = sub.add_parser("show", help="Show a trade's current state (any status)")
    p_show.add_argument("trade_id", type=int)
    p_show.set_defaults(func=cmd_show)

    p_list = sub.add_parser("list-drafts", help="List all draft trades")
    p_list.add_argument("--symbol", default=None)
    p_list.set_defaults(func=cmd_list_drafts)

    p_publish = sub.add_parser("publish", help="Publish a draft trade — flips to open, fires one Telegram alert")
    p_publish.add_argument("trade_id", type=int)
    p_publish.set_defaults(func=cmd_publish)

    p_discard = sub.add_parser("discard", help="Hard-delete a still-draft trade")
    p_discard.add_argument("trade_id", type=int)
    p_discard.set_defaults(func=cmd_discard)

    p_adjust = sub.add_parser("adjust", help="Adjust an open trade's legs")
    p_adjust.add_argument("trade_id", type=int)
    p_adjust.add_argument("--type", required=True, choices=list(_ADJ_TYPES))
    p_adjust.add_argument("--note", default="")
    p_adjust.add_argument("--leg", action="append", default=[])
    p_adjust.add_argument("--legs", action="append", default=[],
                           help="shorthand, see 'create --legs'")
    p_adjust.set_defaults(func=cmd_adjust)

    p_exit = sub.add_parser("exit", help="Fully exit an open trade (one --leg/--legs entry per current leg)")
    p_exit.add_argument("trade_id", type=int)
    p_exit.add_argument("--note", default="")
    p_exit.add_argument("--leg", action="append", default=[],
                         help="type=...,strike=...,expiry=...,price_mode=...,price=... "
                              "(or instrument_key=... for EQ) — matched by identity, not position")
    p_exit.add_argument("--legs", action="append", default=[],
                         help="shorthand, see 'create --legs' — SIDE/LOTS parsed but ignored "
                              "(matched by strike+type/expiry, not side)")
    p_exit.set_defaults(func=cmd_exit)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except CLIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
