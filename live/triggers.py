"""
Trigger evaluators — one class per trigger type.

Each trigger is stateful per (config, symbol):
    t = build_trigger(cfg, "NIFTY50")
    t.refresh()          # call at startup and every REFRESH_CYCLES ticks
    sig = t.check(ltp)   # call on every poll tick; returns signal dict or None

Signal dict keys (common to all triggers):
    trigger_name   str    — from config "name"
    trigger_type   str    — from config "type"
    symbol         str
    ltp            float  — price at the moment of trigger
    indicator_val  float  — the computed indicator value that was crossed/breached
    event          str    — human description e.g. "CROSS UP", "RSI OVERSOLD"
    timeframe      str
    candle_ts             — timestamp of the last DB candle used for computation
    extra          dict   — trigger-specific extra fields (e.g. st_dir for ST)
"""

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from live.signal_engine import compute_supertrend, compute_ema, compute_rsi
from live.trade_suggestions import build_all_trades

_IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseTrigger:
    def __init__(self, cfg: dict, symbol: str):
        self.name          = cfg["name"]
        self.type          = cfg["type"]
        self.symbol        = symbol
        self.timeframe     = cfg["timeframe"]
        self._trades_cfg   = cfg.get("trades", [])          # list; empty = basic alert
        self._cooldown_sec = cfg.get("cooldown_minutes", 0) * 60
        self._last_fired: float | None = None
        self._last_ltp:   float | None = None   # last seen live price; used by refresh()

    def refresh(self):
        """Reload indicator from DB. Override in subclasses."""

    def check(self, ltp: float) -> dict | None:
        """Return a signal dict if the trigger fired, else None."""

    def _signal(self, ltp: float, indicator_val: float,
                event: str, candle_ts=None, extra: dict | None = None) -> dict | None:
        # Cooldown: suppress rapid re-alerts on the same trigger
        if self._cooldown_sec and self._last_fired is not None:
            elapsed = time.time() - self._last_fired
            if elapsed < self._cooldown_sec:
                remaining = int(self._cooldown_sec - elapsed)
                print(f"  [cooldown]  {self.symbol} [{self.name}]  "
                      f"suppressed ({remaining}s remaining)", flush=True)
                return None

        self._last_fired = time.time()
        sig = {
            "trigger_name":  self.name,
            "trigger_type":  self.type,
            "symbol":        self.symbol,
            "timeframe":     self.timeframe,
            "ltp":           ltp,
            "indicator_val": indicator_val,
            "event":         event,
            "candle_ts":     candle_ts,
            **(extra or {}),
        }
        # trades: always a list — empty for basic alerts, 1+ for trade suggestions
        sig["trades"] = build_all_trades(self._trades_cfg, ltp, self.symbol)
        return sig


# ---------------------------------------------------------------------------
# Supertrend cross — fires on LTP crossing ST line in either direction
# ---------------------------------------------------------------------------

class SupertrendCrossTrigger(BaseTrigger):
    def __init__(self, cfg: dict, symbol: str):
        super().__init__(cfg, symbol)
        self.period       = cfg["period"]
        self.multiplier   = cfg["multiplier"]
        self._st_val: float | None = None
        self._st_dir: int   | None = None
        self._st_ts                = None
        self._last_close: float | None = None
        self._prev_above: bool  | None = None

    def refresh(self):
        self._st_val, self._st_dir, self._st_ts, self._last_close = compute_supertrend(
            self.symbol, self.timeframe, self.period, self.multiplier
        )
        baseline = self._last_ltp if self._last_ltp is not None else self._last_close
        self._prev_above = baseline > self._st_val

    def check(self, ltp: float) -> dict | None:
        self._last_ltp = ltp
        if self._st_val is None:
            return None
        curr_above = ltp > self._st_val
        if curr_above == self._prev_above:
            return None
        self._prev_above = curr_above
        return self._signal(
            ltp, self._st_val,
            event="CROSS UP" if curr_above else "CROSS DOWN",
            candle_ts=self._st_ts,
            extra={"st_dir": self._st_dir, "prev_close": self._last_close},
        )

    def summary(self) -> str:
        if self._st_val is None:
            return "not loaded"
        bias = "Bullish" if self._st_dir == 1 else "Bearish"
        return f"ST({self.period},{self.multiplier}) = {self._st_val:,.2f}  [{bias}]"


# ---------------------------------------------------------------------------
# EMA cross — fires on LTP crossing EMA line in either direction
# ---------------------------------------------------------------------------

class EmaCrossTrigger(BaseTrigger):
    def __init__(self, cfg: dict, symbol: str):
        super().__init__(cfg, symbol)
        self.period        = cfg["period"]
        self.direction     = cfg.get("direction")  # "UP", "DOWN", or None (both)
        self._ema_val: float | None = None
        self._ema_ts                = None
        self._last_close: float | None = None
        self._prev_above: bool  | None = None

    def refresh(self):
        self._ema_val, self._ema_ts, self._last_close = compute_ema(
            self.symbol, self.timeframe, self.period
        )
        baseline = self._last_ltp if self._last_ltp is not None else self._last_close
        self._prev_above = baseline > self._ema_val

    def check(self, ltp: float) -> dict | None:
        self._last_ltp = ltp
        if self._ema_val is None:
            return None
        curr_above = ltp > self._ema_val
        if curr_above == self._prev_above:
            return None

        # Direction filter
        if self.direction == "UP" and not curr_above:
            self._prev_above = curr_above
            return None
        if self.direction == "DOWN" and curr_above:
            self._prev_above = curr_above
            return None

        self._prev_above = curr_above
        return self._signal(
            ltp, self._ema_val,
            event="CROSS UP" if curr_above else "CROSS DOWN",
            candle_ts=self._ema_ts,
            extra={"prev_close": self._last_close},
        )

    def summary(self) -> str:
        if self._ema_val is None:
            return "not loaded"
        dir_str   = f"  dir={self.direction}" if self.direction else ""
        trade_str = "  [+trade]" if self._trades_cfg else ""
        return f"EMA{self.period} = {self._ema_val:,.2f}{dir_str}{trade_str}"


# ---------------------------------------------------------------------------
# RSI threshold — fires when RSI crosses below "below" or above "above"
# ---------------------------------------------------------------------------

class RsiThresholdTrigger(BaseTrigger):
    def __init__(self, cfg: dict, symbol: str):
        super().__init__(cfg, symbol)
        self.period         = cfg["period"]
        self.below          = cfg.get("below")   # oversold level  e.g. 35
        self.above          = cfg.get("above")   # overbought level e.g. 70
        self._rsi_val: float | None = None
        self._rsi_ts                = None
        self._was_below: bool | None = None
        self._was_above_ob: bool | None = None

    def refresh(self):
        self._rsi_val, self._rsi_ts = compute_rsi(
            self.symbol, self.timeframe, self.period
        )
        # Do NOT reset _was_* here — RSI crossing state persists across refreshes

    def check(self, ltp: float) -> dict | None:
        if self._rsi_val is None:
            return None

        # Oversold: RSI drops below threshold
        if self.below is not None:
            curr = self._rsi_val < self.below
            if self._was_below is None:
                self._was_below = curr
            elif curr and not self._was_below:
                self._was_below = curr
                return self._signal(ltp, self._rsi_val, "RSI OVERSOLD",
                                    candle_ts=self._rsi_ts,
                                    extra={"rsi_level": self.below})
            else:
                self._was_below = curr

        # Overbought: RSI rises above threshold
        if self.above is not None:
            curr = self._rsi_val > self.above
            if self._was_above_ob is None:
                self._was_above_ob = curr
            elif curr and not self._was_above_ob:
                self._was_above_ob = curr
                return self._signal(ltp, self._rsi_val, "RSI OVERBOUGHT",
                                    candle_ts=self._rsi_ts,
                                    extra={"rsi_level": self.above})
            else:
                self._was_above_ob = curr

        return None

    def summary(self) -> str:
        if self._rsi_val is None:
            return "not loaded"
        parts = [f"RSI{self.period} = {self._rsi_val:.1f}"]
        if self.below:
            parts.append(f"oversold<{self.below}")
        if self.above:
            parts.append(f"overbought>{self.above}")
        return "  ".join(parts)


# ---------------------------------------------------------------------------
# Nifty 500-multiple short strategy
# ---------------------------------------------------------------------------

class Nifty500MultipleTrigger(BaseTrigger):
    """
    Entry    : LTP crosses UP through a 500-multiple.
               Fetches live fut + PE prices from Upstox at entry.
               Opens a trade header row + inserts entry leg rows.

    Exit     : LTP crosses DOWN through (entry_level - exit_distance).
               Reads entry legs from DB; fetches exit prices; inserts exit legs.

    Rollover : On expiry day at ROLLOVER_TIME_IST, for any open trade whose
               entry FUT leg expiry matches today.
               Fetches all 4 prices in one call; inserts rollover_out legs on old
               trade + rollover_in legs on new trade (linked via parent_trade_id).

    check() may return a list of signals (multiple events can fire in the same tick).
    All strategy params live in config trades[0].params.
    """

    def __init__(self, cfg: dict, symbol: str):
        super().__init__(cfg, symbol)
        self._prev_ltp: float | None = None
        self._rolled_today: set[int]  = set()   # trade IDs rolled this session

    def refresh(self):
        pass   # pure LTP-based — no candle data needed

    def summary(self) -> str:
        from db.queries import get_all_open_recommended_trades
        trades = get_all_open_recommended_trades(self.symbol)
        if not trades:
            return "watching 500-multiples (no open positions)"
        levels = ", ".join(f"{t['entry_level']:,.0f}" for t in trades)
        return f"watching 500-multiples — open at: {levels}"

    def check(self, ltp: float):
        self._last_ltp = ltp

        if self._prev_ltp is None:
            self._prev_ltp = ltp
            return None

        prev = self._prev_ltp
        self._prev_ltp = ltp

        from db.queries import (
            get_open_recommended_trade, get_all_open_recommended_trades,
            open_recommended_trade, add_trade_legs,
            close_recommended_trade, get_trade_legs,
        )
        from live.trade_suggestions import build_trade_suggestion

        now_utc   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_ist   = datetime.now(timezone.utc).astimezone(_IST)
        entry_cfg = self._trades_cfg[0] if self._trades_cfg else None
        signals   = []

        # --- Rollover: expiry day + past rollover time ---
        open_trades = get_all_open_recommended_trades(self.symbol)
        if self._past_rollover_time(now_ist):
            for trade in open_trades:
                if trade["id"] in self._rolled_today:
                    continue
                # Determine expiry from the stored FUT entry leg (not trade header)
                legs        = get_trade_legs(trade["id"])
                entry_legs  = [l for l in legs if l["action"] == "entry"]
                fut_leg     = next((l for l in entry_legs if l["instrument_type"] == "FUT"), None)
                if fut_leg and fut_leg.get("expiry_str"):
                    leg_expiry = datetime.strptime(fut_leg["expiry_str"], "%d %b %Y").date()
                    if leg_expiry == now_ist.date():
                        self._rolled_today.add(trade["id"])
                        roll_sig = self._do_rollover(
                            trade, entry_legs, ltp, now_utc, entry_cfg
                        )
                        if roll_sig:
                            signals.append(roll_sig)
            open_trades = get_all_open_recommended_trades(self.symbol)

        # --- Exit: LTP drops to/below exit_level ---
        for trade in open_trades:
            exit_level = trade["exit_level"]
            if prev > exit_level >= ltp:
                legs       = get_trade_legs(trade["id"])
                entry_legs = [l for l in legs if l["action"] == "entry"]
                fut_leg    = next((l for l in entry_legs if l["instrument_type"] == "FUT"), None)
                pe_leg     = next((l for l in entry_legs if l["instrument_type"] == "PE"),  None)

                # Fetch exit prices using stored instrument keys
                prices = self._fetch_prices(
                    fut_leg["instrument_key"] if fut_leg else None,
                    pe_leg["instrument_key"]  if pe_leg  else None,
                )

                # Build and store exit legs
                exit_legs = [
                    {
                        "action": "exit",
                        "side":   "BUY" if leg["side"] == "SELL" else "SELL",
                        "instrument_type": leg["instrument_type"],
                        "instrument_key":  leg["instrument_key"],
                        "strike":          leg["strike"],
                        "expiry_str":      leg["expiry_str"],
                        "lots":            leg["lots"],
                        "lot_size":        leg["lot_size"],
                        "price":           prices.get(leg["instrument_key"]),
                        "ts":              now_utc,
                    }
                    for leg in entry_legs
                ]
                close_recommended_trade(trade["id"], ltp, now_utc, exit_legs=exit_legs)

                # Telegram display
                exit_params = {
                    "entry_level": trade["entry_level"],
                    "exit_level":  trade["exit_level"],
                    "expiry_str":  fut_leg["expiry_str"] if fut_leg else "—",
                    "pe_strike":   int(pe_leg["strike"])  if pe_leg  else 0,
                    "fut_lots":    fut_leg["lots"]         if fut_leg else 1,
                    "pe_lots":     pe_leg["lots"]          if pe_leg  else 2,
                }
                exit_trade = build_trade_suggestion(
                    {"type": "nifty_500_short_exit", "params": exit_params},
                    ltp, self.symbol,
                )
                signals.append(self._make_signal(
                    ltp, exit_level, "500-MULTI EXIT",
                    int(trade["entry_level"]), int(exit_level),
                    [exit_trade] if exit_trade else [],
                ))

        # --- Entry: LTP crosses UP through a 500-multiple ---
        curr_band = int(ltp // 500)
        prev_band = int(prev // 500)
        if curr_band > prev_band and entry_cfg:
            level = curr_band * 500
            existing = get_open_recommended_trade(self.symbol, level)
            if existing is not None:
                print(f"  [500-multi]  {self.symbol}  cross @ {level:,} skipped — "
                      f"open trade id={existing['id']} entered {existing['entry_time']}",
                      flush=True)
            else:
                entry_trade = build_trade_suggestion(entry_cfg, ltp, self.symbol)
                if entry_trade and entry_trade.get("_expiry_date"):
                    pe_strike  = entry_trade.pop("_pe_strike")
                    exp_str    = entry_trade.pop("_expiry_str")
                    near_date  = entry_trade.pop("_expiry_date")
                    exit_level = entry_trade.pop("_exit_level")

                    from live.fo_instruments import nifty_fut_ikey, nifty_pe_ikey, nifty_lot_size
                    from live.upstox_client import get_margin
                    fut_ikey = nifty_fut_ikey(near_date)
                    pe_ikey  = nifty_pe_ikey(near_date, pe_strike)
                    lot_size = nifty_lot_size(near_date) or 0
                    p        = entry_cfg["params"]
                    prices   = self._fetch_prices(fut_ikey, pe_ikey)

                    # Margin at entry (best-effort — None if API unavailable)
                    margin_required = margin_final = None
                    try:
                        m = get_margin([
                            {"instrument_key": fut_ikey, "transaction_type": "SELL",
                             "quantity": p.get("fut_lots", 1) * lot_size,
                             "price": prices.get(fut_ikey) or 0.0},
                            {"instrument_key": pe_ikey,  "transaction_type": "SELL",
                             "quantity": p.get("pe_lots", 2) * lot_size,
                             "price": prices.get(pe_ikey) or 0.0},
                        ])
                        margin_required = m["required_margin"]
                        margin_final    = m["final_margin"]
                    except Exception as e:
                        print(f"  [500-multi]  margin fetch failed: {e}", flush=True)

                    trade_id = open_recommended_trade(
                        self.name, self.symbol, level, ltp, now_utc, exit_level,
                        margin_required=margin_required, margin_final=margin_final,
                    )
                    add_trade_legs(trade_id, [
                        {
                            "action": "entry", "side": "SELL",
                            "instrument_type": "FUT",
                            "instrument_key": fut_ikey,
                            "strike": None, "expiry_str": exp_str,
                            "lots": p.get("fut_lots", 1), "lot_size": lot_size,
                            "price": prices.get(fut_ikey), "ts": now_utc,
                        },
                        {
                            "action": "entry", "side": "SELL",
                            "instrument_type": "PE",
                            "instrument_key": pe_ikey,
                            "strike": pe_strike, "expiry_str": exp_str,
                            "lots": p.get("pe_lots", 2), "lot_size": lot_size,
                            "price": prices.get(pe_ikey), "ts": now_utc,
                        },
                    ])
                    signals.append(self._make_signal(
                        ltp, level, "500-MULTI ENTRY",
                        level, exit_level,
                        [entry_trade],
                    ))
                else:
                    print(f"  [500-multi]  {self.symbol}  "
                          f"expiry unavailable — skip entry @ {level:,}", flush=True)

        if not signals:
            return None
        return signals if len(signals) > 1 else signals[0]

    # ------------------------------------------------------------------ helpers

    def _past_rollover_time(self, now_ist: datetime) -> bool:
        from config import ROLLOVER_TIME_IST
        h, m = ROLLOVER_TIME_IST
        return now_ist.hour > h or (now_ist.hour == h and now_ist.minute >= m)

    def _fetch_prices(self, *ikeys) -> dict:
        """Fetch live prices for given instrument keys. Returns {key: price}."""
        valid = [k for k in ikeys if k]
        if not valid:
            return {}
        try:
            from live.upstox_client import get_ltp as fetch_ltp
            return fetch_ltp(valid)
        except Exception as e:
            print(f"  [500-multi]  price fetch failed: {e}", flush=True)
            return {}

    def _do_rollover(self, trade: dict, entry_legs: list,
                     ltp: float, now_utc: str,
                     entry_cfg: dict | None) -> dict | None:
        """Roll an expiring trade: close old legs, open new month legs."""
        from live.expiry import expiry_cache
        from live.fo_instruments import nifty_fut_ikey, nifty_pe_ikey, nifty_lot_size
        from live.trade_suggestions import build_trade_suggestion
        from db.queries import roll_recommended_trade

        old_fut_leg = next((l for l in entry_legs if l["instrument_type"] == "FUT"), None)
        old_pe_leg  = next((l for l in entry_legs if l["instrument_type"] == "PE"),  None)

        old_fut_key   = old_fut_leg["instrument_key"] if old_fut_leg else None
        old_pe_key    = old_pe_leg["instrument_key"]  if old_pe_leg  else None
        old_pe_strike = int(old_pe_leg["strike"])      if old_pe_leg and old_pe_leg.get("strike") else 0
        old_exp_str   = old_fut_leg["expiry_str"]      if old_fut_leg else None
        fut_lots      = old_fut_leg["lots"]             if old_fut_leg else 1
        pe_lots       = old_pe_leg["lots"]              if old_pe_leg  else 2
        old_lot_size  = old_fut_leg["lot_size"]         if old_fut_leg else 0

        new_expiry = expiry_cache.pick(self.symbol, "monthly", 1)
        if not new_expiry:
            print("  [500-multi]  rollover: new expiry unavailable — skip", flush=True)
            return None

        p             = entry_cfg["params"] if entry_cfg else {}
        min_dist      = ltp * (p.get("min_pe_distance_pct", 3) / 100)
        step          = p.get("strike_step", 500)
        new_pe_strike = int((ltp - min_dist) // step) * step
        new_exit_level = int(trade["entry_level"]) - p.get("exit_distance", 500)
        new_exp_str   = new_expiry.strftime("%d %b %Y")
        new_lot_size  = nifty_lot_size(new_expiry) or 0

        new_fut_key = nifty_fut_ikey(new_expiry)
        new_pe_key  = nifty_pe_ikey(new_expiry, new_pe_strike)

        prices = self._fetch_prices(old_fut_key, old_pe_key, new_fut_key, new_pe_key)

        old_fut_price = prices.get(old_fut_key)
        old_pe_price  = prices.get(old_pe_key)
        new_fut_price = prices.get(new_fut_key)
        new_pe_price  = prices.get(new_pe_key)

        rollover_out_legs = [
            {
                "action": "rollover_out", "side": "BUY",
                "instrument_type": "FUT", "instrument_key": old_fut_key,
                "strike": None, "expiry_str": old_exp_str,
                "lots": fut_lots, "lot_size": old_lot_size,
                "price": old_fut_price, "ts": now_utc,
            },
            {
                "action": "rollover_out", "side": "BUY",
                "instrument_type": "PE", "instrument_key": old_pe_key,
                "strike": old_pe_strike, "expiry_str": old_exp_str,
                "lots": pe_lots, "lot_size": old_lot_size,
                "price": old_pe_price, "ts": now_utc,
            },
        ]
        rollover_in_legs = [
            {
                "action": "rollover_in", "side": "SELL",
                "instrument_type": "FUT", "instrument_key": new_fut_key,
                "strike": None, "expiry_str": new_exp_str,
                "lots": fut_lots, "lot_size": new_lot_size,
                "price": new_fut_price, "ts": now_utc,
            },
            {
                "action": "rollover_in", "side": "SELL",
                "instrument_type": "PE", "instrument_key": new_pe_key,
                "strike": new_pe_strike, "expiry_str": new_exp_str,
                "lots": pe_lots, "lot_size": new_lot_size,
                "price": new_pe_price, "ts": now_utc,
            },
        ]

        # Margin for the new rolled position (best-effort)
        new_margin_required = new_margin_final = None
        try:
            from live.upstox_client import get_margin
            m = get_margin([
                {"instrument_key": new_fut_key, "transaction_type": "SELL",
                 "quantity": fut_lots * new_lot_size, "price": new_fut_price or 0.0},
                {"instrument_key": new_pe_key,  "transaction_type": "SELL",
                 "quantity": pe_lots * new_lot_size,  "price": new_pe_price  or 0.0},
            ])
            new_margin_required = m["required_margin"]
            new_margin_final    = m["final_margin"]
        except Exception as e:
            print(f"  [500-multi]  rollover margin fetch failed: {e}", flush=True)

        new_id = roll_recommended_trade(
            trade["id"],
            exit_ltp=ltp, exit_time=now_utc,
            new_entry_ltp=ltp, new_exit_level=new_exit_level,
            rollover_out_legs=rollover_out_legs,
            rollover_in_legs=rollover_in_legs,
            new_margin_required=new_margin_required,
            new_margin_final=new_margin_final,
        )
        print(f"  [500-multi]  rolled trade {trade['id']} → {new_id}  "
              f"({old_exp_str} → {new_exp_str})", flush=True)

        roll_trade = build_trade_suggestion({
            "type": "nifty_500_short_rollover",
            "params": {
                **p,
                "old_expiry_str": old_exp_str,
                "new_expiry_str": new_exp_str,
                "old_pe_strike":  old_pe_strike,
                "new_pe_strike":  new_pe_strike,
                "old_fut_price":  old_fut_price,
                "old_pe_price":   old_pe_price,
                "new_fut_price":  new_fut_price,
                "new_pe_price":   new_pe_price,
                "fut_lots":       fut_lots,
                "pe_lots":        pe_lots,
                "entry_level":    int(trade["entry_level"]),
            },
        }, ltp, self.symbol)

        return self._make_signal(
            ltp, ltp, "500-MULTI ROLLOVER",
            int(trade["entry_level"]), new_exit_level,
            [roll_trade] if roll_trade else [],
        )

    def _make_signal(self, ltp: float, indicator_val: float, event: str,
                     entry_level: int, exit_level: int, trades: list) -> dict:
        return {
            "trigger_name":  self.name,
            "trigger_type":  self.type,
            "symbol":        self.symbol,
            "timeframe":     self.timeframe,
            "ltp":           ltp,
            "indicator_val": float(indicator_val),
            "event":         event,
            "entry_level":   entry_level,
            "exit_level":    exit_level,
            "candle_ts":     None,
            "trades":        trades,
        }


# ---------------------------------------------------------------------------
# Confluence helpers
# ---------------------------------------------------------------------------

def _cross_label(cross_cfg: dict) -> str:
    ind = cross_cfg["indicator"]
    if ind == "ema":
        return f"EMA{cross_cfg['period']}"
    if ind == "supertrend":
        return f"ST({cross_cfg['period']},{cross_cfg['multiplier']})"
    return ind.upper()


def _eval_confirm(cond: dict, symbol: str, timeframe: str,
                  ltp: float, cross_dir: str) -> bool:
    """
    Evaluate one confirm condition. Returns True if the signal should proceed.

    Supported types:
        supertrend_direction  — ST direction must match cross direction
        price_below_day_high  — LTP < today's intraday high (from 5m candles)
        price_above_day_low   — LTP > today's intraday low  (from 5m candles)
    """
    ctype = cond["type"]

    if ctype == "supertrend_direction":
        _, st_dir, _, _ = compute_supertrend(
            symbol, timeframe, cond["period"], cond["multiplier"]
        )
        expected = cond.get("expected")          # "bullish" | "bearish" | absent
        if expected == "bullish":
            return st_dir == 1
        if expected == "bearish":
            return st_dir == -1
        return st_dir == (1 if cross_dir == "UP" else -1)   # match cross direction

    if ctype in ("price_below_day_high", "price_above_day_low"):
        from db.queries import get_candles
        df = get_candles(symbol, "5m", limit=90)   # 90 × 5m = 7.5h covers full session
        if df.empty:
            return True
        today = datetime.now(timezone.utc).date()
        today_df = df[df["ts"].dt.date == today]
        if today_df.empty:
            return True
        if ctype == "price_below_day_high":
            return ltp < float(today_df["high"].max())
        return ltp > float(today_df["low"].min())

    return True   # unknown condition type → don't block


# ---------------------------------------------------------------------------
# Confluence cross — cross indicator + N confirm conditions (AND-gated)
# ---------------------------------------------------------------------------

class ConfluenceCrossTrigger(BaseTrigger):
    """
    Fires when the cross indicator crosses AND all confirm conditions pass.

    Config keys:
        cross:     {"indicator": "ema"|"supertrend", "period": N, ["multiplier": M]}
        confirm:   list of condition dicts — all must pass at fire time
        direction: "UP" | "DOWN" | None  (filter to one crossing direction)

    Example:
        {
            "type":      "confluence_cross",
            "timeframe": "15m",
            "cross":     {"indicator": "ema", "period": 20},
            "confirm":   [
                {"type": "supertrend_direction", "period": 10, "multiplier": 3.0},
                {"type": "price_below_day_high"},
            ],
            "direction": "DOWN",
        }
    """

    def __init__(self, cfg: dict, symbol: str):
        super().__init__(cfg, symbol)
        self._cross_cfg   = cfg["cross"]
        self._confirm_cfg = cfg.get("confirm", [])
        self.direction    = cfg.get("direction")

        self._cross_val:  float | None = None
        self._cross_ts                 = None
        self._last_close: float | None = None
        self._prev_above: bool  | None = None
        self._st_dir:     int   | None = None   # only set when cross=supertrend

    def refresh(self):
        ind = self._cross_cfg["indicator"]
        if ind == "ema":
            self._cross_val, self._cross_ts, self._last_close = compute_ema(
                self.symbol, self.timeframe, self._cross_cfg["period"]
            )
        elif ind == "supertrend":
            self._cross_val, self._st_dir, self._cross_ts, self._last_close = (
                compute_supertrend(
                    self.symbol, self.timeframe,
                    self._cross_cfg["period"], self._cross_cfg["multiplier"]
                )
            )
        baseline = self._last_ltp if self._last_ltp is not None else self._last_close
        self._prev_above = baseline > self._cross_val

    def check(self, ltp: float) -> dict | None:
        self._last_ltp = ltp
        if self._cross_val is None:
            return None

        curr_above = ltp > self._cross_val
        if curr_above == self._prev_above:
            return None

        cross_dir = "UP" if curr_above else "DOWN"

        # Direction filter
        if self.direction == "UP" and cross_dir == "DOWN":
            self._prev_above = curr_above
            return None
        if self.direction == "DOWN" and cross_dir == "UP":
            self._prev_above = curr_above
            return None

        # Evaluate all confirm conditions — any failure suppresses the signal
        for cond in self._confirm_cfg:
            if not _eval_confirm(cond, self.symbol, self.timeframe, ltp, cross_dir):
                self._prev_above = curr_above
                print(f"  [confluence]  {self.symbol} [{self.name}]  "
                      f"{cross_dir} suppressed — {cond['type']} not confirmed", flush=True)
                return None

        self._prev_above = curr_above
        extra = {
            "prev_close":   self._last_close,
            "cross_label":  _cross_label(self._cross_cfg),
            "confirmed_by": [c["type"] for c in self._confirm_cfg],
        }
        if self._st_dir is not None:
            extra["st_dir"] = self._st_dir

        return self._signal(
            ltp, self._cross_val,
            event=f"CROSS {cross_dir}",
            candle_ts=self._cross_ts,
            extra=extra,
        )

    def summary(self) -> str:
        if self._cross_val is None:
            return "not loaded"
        confirm_str = " + ".join(c["type"] for c in self._confirm_cfg) or "no filters"
        return f"{_cross_label(self._cross_cfg)} = {self._cross_val:,.2f}  [{confirm_str}]"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type] = {
    "supertrend_cross":   SupertrendCrossTrigger,
    "ema_cross":          EmaCrossTrigger,
    "rsi_threshold":      RsiThresholdTrigger,
    "confluence_cross":   ConfluenceCrossTrigger,
    "nifty_500_multiple": Nifty500MultipleTrigger,
}


def build_trigger(cfg: dict, symbol: str) -> BaseTrigger:
    cls = _REGISTRY.get(cfg["type"])
    if cls is None:
        raise ValueError(
            f"Unknown trigger type: {cfg['type']!r}. "
            f"Valid types: {list(_REGISTRY)}"
        )
    return cls(cfg, symbol)
