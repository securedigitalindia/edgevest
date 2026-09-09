# ============================================================
#  Drishti — live/option_chain_capture.py
#  5-minute full option-chain snapshot capture.
#
#  Standalone data-capture mechanism, separate from the 5s get_ltp()
#  poll loop — feeds the option_chain_5m table only. Does not touch
#  ticks / price_cache / candles_* or the trigger/alert pipeline.
#
#  Captures the full chain (all strikes, both CE/PE) for the "weekly",
#  "monthly", and "quarterly" expiry buckets — a different rank depth per
#  type (weekly 0-3, monthly 0-2, quarterly 0-1; recomputed every snapshot;
#  see the dated comments above SYMBOLS/EXPIRY_RANKS below for why) via
#  Upstox's put-call option-chain endpoint. This is the dataset
#  behind the calendar-spread analysis tool (premium diff between two
#  expiries at the same strike, tracked over time as spot moves and near
#  expiry approaches) and the PE ratio diagonal strategy's backtest data.
#
#  SDK response shape (confirmed against the installed upstox_client
#  package and a live API call before writing this parser):
#
#    OptionsApi.get_put_call_option_chain(instrument_key, expiry_date)
#      -> GetOptionChainResponse
#           .status : str
#           .data   : list[OptionStrikeData]
#
#    OptionStrikeData
#      .strike_price          : float
#      .underlying_spot_price : float   (spot at capture time — no separate LTP call needed)
#      .expiry                : datetime
#      .call_options           : PutCallOptionChainData | None
#      .put_options            : PutCallOptionChainData | None
#
#    PutCallOptionChainData
#      .instrument_key : str
#      .market_data    : MarketData      (ltp, oi, volume, close_price, bid/ask, prev_oi)
#      .option_greeks  : AnalyticsData   (vega, theta, gamma, delta, iv, pop)
#
#  Usage (called from live/poller.py on its own 5-min timer):
#      from live import option_chain_capture
#      option_chain_capture.run_capture()
# ============================================================

from datetime import date, datetime, timezone

import upstox_client

from config import UPSTOX_ACCESS_TOKEN, UPSTOX_INSTRUMENT_KEYS
from live.expiry import expiry_cache
from db.queries import write_option_chain_snapshot

# Only NIFTY50 has an active options strategy today — don't over-generalise
# to other symbols until there's a reason to.
#
# 2026-09-09: widened from weekly+monthly ranks 0-2 (6 Upstox calls/snapshot)
# to all three types at ranks 0-4 (15 calls/snapshot) to fix two real bugs —
# see git history for the full writeup. Re-tightened the SAME day, once it
# was clear the uniform 5-deep rank list was applying one type's fix depth
# to all three: a per-type EXPIRY_RANKS (9 calls/snapshot) keeps both actual
# fixes intact and only trims the headroom that was never the fix itself.
#
# - weekly: 0-3 (was 0-4). The PE ratio diagonal strategy
#   (docs/prd/pe-ratio-diagonal-strategy.md) skips the imminent weekly expiry
#   when its DTE<=1 relative to entry day — if that skipped expiry is itself
#   weekly-classified (not a month-end date, which is bucketed as "monthly"
#   instead and doesn't consume a weekly rank), the strategy's own 3 needed
#   expiries land on capture ranks 1/2/3, and rank 3 was never captured.
#   Confirmed: this silently understated one entry's true debit by >2x before
#   a live-Upstox-fallback patched the analysis side — capturing rank 3
#   closes the actual root cause instead of leaning on that fallback. Ranks
#   0-2 only ever get skipped by at most one (the DTE<=1 rule never skips
#   more than the single imminent expiry), so rank 3 is the true requirement
#   — rank 4 was pure headroom, never the fix, and is dropped here.
# - monthly: 0-2 (unchanged from before the whole 2026-09-09 widening) — the
#   weekly-rank bug above never implicated monthly at all; it only ever
#   inherited depth 0-4 as a side effect of one shared rank list applying to
#   every type. 0-2 was always sufficient for this type.
# - quarterly: 0-1 (was 0-4). NIFTY's real expiry calendar has a THIRD
#   Upstox type, "quarterly" — and it isn't quarterly-spaced in practice
#   near-term; 2026-09-29 (otherwise the natural next expiry after
#   2026-09-22, ~7 days later) is bucketed as quarterly[0], not monthly.
#   Merged-cadence logic only ever read weekly+monthly, so 2026-09-29 was
#   invisible to it entirely — resolving a Sep-7 entry's 3rd expiry jumped
#   straight to 2026-10-27 (monthly[0], 50 days out) instead of the real
#   next expiry only ~22 days out, producing an entry priced against a far
#   longer-dated (and far more expensive) contract than intended. The fix
#   only ever needed quarterly[0] to exist — rank 1 kept as one unit of
#   headroom, ranks 2-4 dropped as unused margin. See
#   db.queries.get_merged_cadence_dates for the matching query-side fix.
SYMBOLS       = ["NIFTY50"]
EXPIRY_RANKS  = {
    "weekly":    [0, 1, 2, 3],
    "monthly":   [0, 1, 2],
    "quarterly": [0, 1],
}

_api = None


def _get_api() -> upstox_client.OptionsApi:
    """Singleton Upstox OptionsApi client — same construction pattern as live/expiry.py."""
    global _api
    if _api is None:
        cfg = upstox_client.Configuration()
        cfg.access_token = UPSTOX_ACCESS_TOKEN
        _api = upstox_client.OptionsApi(upstox_client.ApiClient(cfg))
    return _api


def _boundary_ts(now_utc: datetime | None = None) -> str:
    """
    Round current UTC time down to the nearest 5-min mark (:00, :05, ... :55).

    NSE market-open-aligned 5-min candle boundaries (09:15, 09:20, ... IST)
    coincide exactly with plain clock-aligned 5-min boundaries in UTC, since
    the IST offset (5h30m = 330 min) is itself a multiple of 5. Rounding
    down like this gives a deterministic, restart-safe slot timestamp —
    the UNIQUE(ts, symbol, expiry_date, strike, opt_type) constraint on
    option_chain_5m relies on repeated captures within the same slot
    producing the same ts.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    floor_minute = (now_utc.minute // 5) * 5
    boundary = now_utc.replace(minute=floor_minute, second=0, microsecond=0)
    return boundary.strftime("%Y-%m-%dT%H:%M:%SZ")


def _capture_expiry(symbol: str, ikey: str, expiry_type: str, rank: int, ts: str) -> list[dict]:
    """Fetch and parse one expiry's full option chain. Returns a list of row dicts."""
    expiry_date: date | None = expiry_cache.pick(symbol, expiry_type, rank)
    if expiry_date is None:
        print(f"  [option_chain_capture] {symbol} {expiry_type}[{rank}] "
              f"— no expiry available yet, skipping", flush=True)
        return []

    api  = _get_api()
    resp = api.get_put_call_option_chain(ikey, str(expiry_date))
    strikes = resp.data or []

    rows: list[dict] = []
    for s in strikes:
        spot = s.underlying_spot_price
        if spot is None:
            continue
        for opt_type, opt in (("CE", s.call_options), ("PE", s.put_options)):
            if opt is None:
                continue
            md     = opt.market_data
            greeks = opt.option_greeks
            rows.append({
                "ts":          ts,
                "symbol":      symbol,
                "spot_ltp":    float(spot),
                "expiry_type": expiry_type,
                "expiry_rank": rank,
                "expiry_date": expiry_date.strftime("%Y-%m-%d"),
                "strike":      float(s.strike_price),
                "opt_type":    opt_type,
                "ltp":         float(md.ltp) if md and md.ltp is not None else None,
                "oi":          float(md.oi) if md and md.oi is not None else None,
                "iv":          float(greeks.iv) if greeks and greeks.iv is not None else None,
            })
    return rows


def capture_symbol(symbol: str, ts: str | None = None) -> list[dict]:
    """
    Capture weekly, monthly, and quarterly buckets (per-type rank depth,
    see EXPIRY_RANKS above) for one symbol. Each expiry fetch is
    independently guarded — one bad rank/expiry/API error does not drop
    the rest of the snapshot.
    """
    ikey = UPSTOX_INSTRUMENT_KEYS.get(symbol)
    if not ikey:
        print(f"  [option_chain_capture] {symbol} — no UPSTOX_INSTRUMENT_KEYS entry, skipping", flush=True)
        return []

    ts = ts or _boundary_ts()
    rows: list[dict] = []
    for expiry_type, ranks in EXPIRY_RANKS.items():
        for rank in ranks:
            try:
                rows.extend(_capture_expiry(symbol, ikey, expiry_type, rank, ts))
            except Exception as e:
                print(f"  [option_chain_capture] {symbol} {expiry_type}[{rank}] fetch failed — {e}", flush=True)
    return rows


def run_capture() -> int:
    """
    Full sweep: all SYMBOLS x every (expiry_type, rank) pair in EXPIRY_RANKS
    (9 calls/snapshot: weekly 0-3, monthly 0-2, quarterly 0-1), written
    in one batch. Intended to be called once every 5 min from the poller's
    main loop, wrapped in try/except by the caller so a failure here never
    crashes the poll loop.

    Returns number of rows written (0 if nothing captured).
    """
    ts = _boundary_ts()
    all_rows: list[dict] = []
    for symbol in SYMBOLS:
        all_rows.extend(capture_symbol(symbol, ts))

    if not all_rows:
        print(f"  [option_chain_capture] no rows captured for ts={ts}", flush=True)
        return 0

    written = write_option_chain_snapshot(all_rows)
    print(f"  [option_chain_capture] ts={ts}  captured {len(all_rows)} row(s), wrote {written}", flush=True)
    return written
