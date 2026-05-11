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

from live.signal_engine import compute_supertrend, compute_ema, compute_rsi
from live.trade_suggestions import build_all_trades


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
    "supertrend_cross": SupertrendCrossTrigger,
    "ema_cross":        EmaCrossTrigger,
    "rsi_threshold":    RsiThresholdTrigger,
    "confluence_cross": ConfluenceCrossTrigger,
}


def build_trigger(cfg: dict, symbol: str) -> BaseTrigger:
    cls = _REGISTRY.get(cfg["type"])
    if cls is None:
        raise ValueError(
            f"Unknown trigger type: {cfg['type']!r}. "
            f"Valid types: {list(_REGISTRY)}"
        )
    return cls(cfg, symbol)
