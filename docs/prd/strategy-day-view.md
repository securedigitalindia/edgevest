# Strategy Day View (Strategies dashboard → day-entry strategies)

**Status**: v1 built on `feature/strategy-day-view`, 2026-11-12, uncommitted. Extends `docs/prd/admin-strategies-dashboard.md` (read its Non-goals — they apply here too).

## Problem
The Strategies dashboard only knew weekly-window strategies with an exit. The user researches **day-entry** strategies (enter on the first touch of a 100-multiple, no exit rule) and needs to see, for any day, what the position did before and after the entry, for the entry strike and its neighbours — and to watch today live. This was proven as a shareable artifact (`backend/analysis/strategy_viewer/`); this PRD ships it in-app.

## Goal / done
An admin opens `/profile/strategies/<id>` for a day-entry strategy and sees: a day picker (every captured day, newest = LIVE), PE/CE variant, entry strike (touch level ± 1000 in 100s), days before (−1..−7) / after (+1..+30, or **To live**), and one stacked chart — NIFTY on top, below it net debit / P&L / leg premiums — plus entry tiles, and a table comparing all 21 entry strikes. Today's day refreshes every minute.

## Non-goals
- Not a trading signal: no recommendation row, no Telegram, admin only (same routes' `require_role`).
- No exit rules, costs, slippage, margin. Last-traded prices only (no bid/ask).
- **Not 5-second live option prices (v2).** "Live" = the poller's 5-minute chain capture (≤ ~5 min old) plus the NIFTY "now" point from the shared 5 s price poll (`usePrices`). True live leg prices would need the selected entry's instrument keys added to the poller's `_all_ikeys` (see the poller-data-flow skill); deferred, not required to ship.
- No paper-trade log / persistence of entries (offered, not requested).

## Mechanics
- **Definitions**: `backend/strategies/day_strategies.py` (`DAY_STRATEGIES`) is the single source of truth, shared with the artifact builder. A strategy = entry rule + signed-quantity legs (`qty` +buy/−sell, strike offset, expiry `M+k`) + variants + strike offsets. Net debit = Σ qty·price; P&L = debit now − debit at entry. Adding a strategy = one entry there (no page change). A new entry rule or weekly expiry type = extend `day_view.py`.
- **Engine**: `backend/strategies/day_view.py` — pure functions over `option_chain_5m`. Entry = first 5-min snapshot within `near`=10 pts of a multiple of `step`=100, or that jumped through one. Spot of a snapshot = `MAX(spot_ltp)` of its rows (the chain stores a few slightly different spot values per capture; max is the convention used by every published artifact — **changing it moves touch times; bump the cache version if you do**). Entry prices wait up to 1 hour for a leg's first trade (`lag` minutes shown). Window = 7 calendar days before .. 30 after the entry day; entry day at 5 min, ±2 trading days 15 min, the rest hourly (payload ≈ 65–100 KB per day+variant).
- **Performance**: leg prices come from one `strike IN (…)` range query per (expiry, option type) using `INDEXED BY idx_option_chain_5m_strike_expiry` — the planner otherwise picks the (symbol, ts) index and is ~4× slower; monthly expiries via GROUP BY on the (symbol, expiry_type, expiry_date) index (DISTINCT was 12 s). Cold compute ≈ 5 s.
- **Cache**: a day is cached in `strategy_backtest_windows` (key `dayview#v1_<id>_<variant>`) only once the data has run 30 days past it; today/unsettled days are recomputed, held 45 s in-process. Day list cached 30 s. Same invalidation caveat as the weekly cache (a late backfill is not auto-detected; `DELETE` the row).
- **API** (admin only, see `docs/apis.md`): `GET /api/strategies` now carries `kind: "window" | "day_entry"`; `GET /api/strategies/<id>/days`; `GET /api/strategies/<id>/day?date=&variant=`.
- **Frontend**: `Strategies.jsx` renders `DayView.jsx` for `kind === "day_entry"` (no config form). The chart is a direct port of the artifact's SVG (`dayChartSvg.js` + `DayChart.jsx`) — parity with the artifact, not a charting-library approximation.

## Data caveats (shown in the UI as reasons)
The stored chain is what it is: 24 Aug–1 Sep entries cannot be priced (the Sep-29 expiry was never stored); far-from-spot strikes of far expiries are stored with price 0 until they trade; the chain keeps only a window of strikes around spot. A skipped entry shows its reason. Could be backfilled from Upstox expired-contract history (not done; access unverified). Lot 65 unverified.

## Open questions
1. True 5 s leg prices (v2) — worth the extra polling?
2. Paper-trade log of each day's entry for tracking?
3. Stage an entry as a draft recommendation via the existing draft workflow?
4. Backfill Aug/early-Sep from Upstox.
