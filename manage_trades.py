#!/usr/bin/env python3
"""
Interactive CLI for manual trade management.

Usage:
    python manage_trades.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from math import gcd
from functools import reduce
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_DIV  = "─" * 54
_DIV2 = "─" * 30

VALID_SYMBOLS = ["NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
VALID_TYPES   = ["PE", "CE", "FUT", "EQ"]


# ─────────────────────────────────────────────────────────────────
# Low-level input helpers
# ─────────────────────────────────────────────────────────────────

def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f"  [{default}]" if default is not None else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\n  Interrupted. Goodbye.\n")
        sys.exit(0)
    return val if val else (default or "")


def _ask_choice(prompt: str, choices: list[str]) -> str:
    choices_upper = [c.upper() for c in choices]
    while True:
        val = _ask(f"{prompt}  ({' / '.join(choices)})").upper()
        if val in choices_upper:
            return val
        print(f"    ✗  Enter one of: {', '.join(choices)}")


def _ask_float(prompt: str) -> float:
    while True:
        val = _ask(prompt)
        try:
            return float(val)
        except ValueError:
            print("    ✗  Enter a valid number  (e.g. 1548.50)")


def _ask_int(prompt: str, min_val: int = 1) -> int:
    while True:
        val = _ask(prompt)
        try:
            v = int(val)
            if v < min_val:
                raise ValueError
            return v
        except ValueError:
            print(f"    ✗  Enter a whole number ≥ {min_val}")


def _confirm(prompt: str = "Confirm?") -> bool:
    val = _ask(f"{prompt}  (y / n)").lower()
    return val in ("y", "yes")


# ─────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────

def _fmt_ist(utc_str: str) -> str:
    try:
        dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).strftime("%d %b %Y  %H:%M IST")
    except Exception:
        return utc_str


def _base_pos(legs: list[dict]) -> int:
    lots = [l["lots"] for l in legs if l.get("lots", 0) > 0]
    return reduce(gcd, lots) if lots else 1


def _leg_short(leg: dict) -> str:
    strike = f"{int(leg['strike']):,} " if leg.get("strike") else ""
    return (f"{leg['side']:<4}  {strike}{leg['instrument_type']}"
            f"  {leg['lots']}L  @{leg['price']:,.2f}")


def _print_open_trades(trades: list, legs_by_id: dict) -> None:
    if not trades:
        print("\n  No open trades found.\n")
        return
    print()
    for i, t in enumerate(trades, 1):
        entry_legs = legs_by_id[t["id"]]
        n_pos      = _base_pos(entry_legs)
        pos_str    = f"  ×{n_pos} pos" if n_pos > 1 else ""
        print(f"  {i}.  {t['symbol']:<12}  entered {_fmt_ist(t['entry_time'])}{pos_str}")
        for leg in entry_legs:
            print(f"        {_leg_short(leg)}")
        print()


# ─────────────────────────────────────────────────────────────────
# CREATE flow
# ─────────────────────────────────────────────────────────────────

def _collect_legs() -> list[dict]:
    legs = []
    print(f"\n  {_DIV2}")
    print("  Add legs  —  leave Side blank when done\n")

    leg_num = 1
    while True:
        print(f"  Leg {leg_num}")
        side = _ask("    Side  (BUY / SELL  or blank to finish)").upper()
        if not side:
            if not legs:
                print("    ✗  At least one leg is required.\n")
                continue
            break
        if side not in ("BUY", "SELL"):
            print("    ✗  Enter BUY or SELL\n")
            continue

        itype = _ask_choice("    Type", VALID_TYPES)

        strike = None
        if itype in ("PE", "CE"):
            strike = _ask_int("    Strike  (e.g. 57000)")

        expiry = None
        if itype in ("PE", "CE", "FUT"):
            expiry = _ask("    Expiry  (e.g. May 2026  or  26 May 2026)")
            if not expiry:
                print("    ✗  Expiry is required for options/futures\n")
                continue

        lots  = _ask_int("    Lots")
        price = _ask_float("    Entry price")

        leg = {"side": side, "type": itype, "lots": lots, "price": price}
        if strike:
            leg["strike"] = strike
        if expiry:
            leg["expiry"] = expiry

        legs.append(leg)
        print(f"    ✓  Leg {leg_num} added\n")
        leg_num += 1

    return legs


def cli_create() -> None:
    from live.manual_trade import add_manual_trade

    print(f"\n{_DIV}")
    print("  Create New Trade")
    print(_DIV)

    print(f"\n  Symbols: {', '.join(VALID_SYMBOLS)}")
    while True:
        symbol = _ask("  Symbol").upper()
        if symbol in VALID_SYMBOLS:
            break
        print(f"    ✗  Unknown symbol. Supported: {', '.join(VALID_SYMBOLS)}")

    legs = _collect_legs()
    note = _ask("\n  Note  (optional, press Enter to skip)")

    # Summary
    n_pos = _base_pos([{"lots": l["lots"]} for l in legs])
    print(f"\n  {_DIV2}")
    print(f"  Summary  —  {symbol}" + (f"  ×{n_pos} positions" if n_pos > 1 else ""))
    print(f"  {_DIV2}")
    for leg in legs:
        strike = f"{leg['strike']:,} " if leg.get("strike") else ""
        expiry = f"   ({leg['expiry']})" if leg.get("expiry") else ""
        print(f"    {leg['side']:<4}  {strike}{leg['type']}  {leg['lots']}L"
              f"  @{leg['price']:,.2f}{expiry}")
    if note:
        print(f"  Note: {note}")
    print()

    if not _confirm("  Create trade and send Telegram alert?"):
        print("  Cancelled.\n")
        return

    print("\n  Processing ...\n")
    trade_id = add_manual_trade(symbol, legs, note)
    print(f"\n  ✅  Trade created  (id={trade_id})  —  alert sent to Telegram.\n")


# ─────────────────────────────────────────────────────────────────
# EXIT flow
# ─────────────────────────────────────────────────────────────────

def cli_exit_trade() -> None:
    from live.manual_trade import close_manual_trade
    from db.queries import get_all_open_trades, get_trade_legs

    print(f"\n{_DIV}")
    print("  Exit a Trade")
    print(_DIV)

    trades     = get_all_open_trades()
    legs_by_id = {
        t["id"]: [l for l in get_trade_legs(t["id"]) if l["action"] == "entry"]
        for t in trades
    }

    _print_open_trades(trades, legs_by_id)

    if not trades:
        return

    # Select trade
    while True:
        sel = _ask(f"  Select trade  (1 – {len(trades)},  0 to cancel)")
        try:
            idx = int(sel)
        except ValueError:
            continue
        if idx == 0:
            print("  Cancelled.\n")
            return
        if 1 <= idx <= len(trades):
            break
        print(f"    ✗  Enter a number between 1 and {len(trades)}")

    trade      = trades[idx - 1]
    entry_legs = legs_by_id[trade["id"]]
    n_pos      = _base_pos(entry_legs)

    print(f"\n  {_DIV2}")
    print(f"  {trade['symbol']}" + (f"  ×{n_pos} pos" if n_pos > 1 else ""))
    print(f"  {_DIV2}")
    print("  Enter exit price for each leg:\n")

    exit_prices: list[float] = []
    for i, leg in enumerate(entry_legs, 1):
        label = _leg_short(leg)
        price = _ask_float(f"  Leg {i}  {label}  →  exit price")
        exit_prices.append(price)

    note = _ask("\n  Note  (optional, press Enter to skip)")

    # P&L preview
    print(f"\n  {_DIV2}")
    print(f"  Exit Summary  —  {trade['symbol']}")
    print(f"  {_DIV2}")
    total_pnl = 0.0
    for leg, exit_p in zip(entry_legs, exit_prices):
        qty       = leg["lots"] * (leg["lot_size"] or 1)
        entry_p   = leg["price"] or 0
        leg_pnl   = (entry_p - exit_p) * qty if leg["side"] == "SELL" \
                    else (exit_p - entry_p) * qty
        total_pnl += leg_pnl
        strike    = f"{int(leg['strike']):,} " if leg.get("strike") else ""
        print(f"    {leg['side']:<4}  {strike}{leg['instrument_type']}  "
              f"{leg['lots']}L   ₹{entry_p:,.2f}  →  ₹{exit_p:,.2f}"
              f"   (₹{leg_pnl:+,.0f})")
    print(f"\n    Net P&L  ₹{total_pnl:+,.0f}\n")

    if not _confirm("  Confirm exit and send Telegram alert?"):
        print("  Cancelled.\n")
        return

    print("\n  Processing ...\n")
    close_manual_trade(trade["id"], exit_prices, note)
    print(f"\n  ✅  Trade closed  —  alert sent to Telegram.\n")


# ─────────────────────────────────────────────────────────────────
# Main menu
# ─────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{'═' * 54}")
    print("   Drishti  —  Manual Trade Manager")
    print(f"{'═' * 54}")

    while True:
        print("\n  What would you like to do?")
        print("    1.  Create new trade")
        print("    2.  Exit an existing trade")
        print("    3.  Quit\n")

        choice = _ask("  Choice").strip()

        if choice == "1":
            cli_create()
        elif choice == "2":
            cli_exit_trade()
        elif choice in ("3", "q", "quit", "exit"):
            print("\n  Goodbye.\n")
            break
        else:
            print("  ✗  Enter 1, 2, or 3")


if __name__ == "__main__":
    main()
