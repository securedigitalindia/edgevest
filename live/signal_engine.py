"""
Indicator compute functions.

Each function returns the indicator value PLUS the last candle's close price.
The close price is used by triggers to initialize the price-side baseline
(above/below indicator) from the last closed candle — not from the first
live tick. This ensures gap-down/gap-up scenarios fire an alert immediately
on the first poll tick rather than being silently missed.
"""

import pandas_ta as ta
from db.queries import get_candles


def compute_supertrend(
    symbol: str, timeframe: str, period: int, multiplier: float
) -> tuple[float, int, object, float]:
    """
    Returns (st_value, direction, last_candle_ts, last_close).
    direction: 1 = bullish (close above ST line), -1 = bearish.
    last_close: close price of the last completed candle.
    """
    df = get_candles(symbol, timeframe, limit=300)

    if df.empty or len(df) < period + 5:
        raise ValueError(
            f"Not enough {timeframe} candles for {symbol}. "
            "Run: python poller.py bootstrap"
        )

    st = ta.supertrend(df["high"], df["low"], df["close"],
                       length=period, multiplier=multiplier)

    st_col  = next(c for c in st.columns
                   if c.startswith("SUPERT_") and not any(x in c for x in ("_d", "_s", "_l")))
    std_col = next(c for c in st.columns if c.startswith("SUPERTd_"))

    return (
        float(st[st_col].iloc[-1]),
        int(st[std_col].iloc[-1]),
        df["ts"].iloc[-1],
        float(df["close"].iloc[-1]),
    )


def compute_ema(symbol: str, timeframe: str, period: int) -> tuple[float, object, float]:
    """
    Returns (ema_value, last_candle_ts, last_close).
    last_close: close price of the last completed candle.
    """
    df = get_candles(symbol, timeframe, limit=max(period * 3, 100))

    if df.empty or len(df) < period + 5:
        raise ValueError(
            f"Not enough {timeframe} candles for {symbol} to compute EMA{period}. "
            "Run: python poller.py bootstrap"
        )

    ema = ta.ema(df["close"], length=period)
    return float(ema.iloc[-1]), df["ts"].iloc[-1], float(df["close"].iloc[-1])


def compute_rsi(symbol: str, timeframe: str, period: int) -> tuple[float, object]:
    """
    Returns (rsi_value, last_candle_ts).
    RSI triggers use candle-level state (not LTP) so last_close is not needed.
    """
    df = get_candles(symbol, timeframe, limit=max(period * 3 + 50, 150))

    if df.empty or len(df) < period + 5:
        raise ValueError(
            f"Not enough {timeframe} candles for {symbol} to compute RSI{period}. "
            "Run: python poller.py bootstrap"
        )

    rsi = ta.rsi(df["close"], length=period)
    return float(rsi.iloc[-1]), df["ts"].iloc[-1]
