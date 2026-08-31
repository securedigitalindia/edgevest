# Monthly Recommendation Report

> **Revised 2026-08-26**: originally shipped admin-only; the founder then asked for client access too. `GET /api/reports/monthly` is now `@require_login` (any authenticated role), and the "Monthly Report" nav entry lives in the common `/profile` section, not the admin-only one. The report's *content* is unchanged — it's still the platform-wide `recommended_trades` aggregate (not account-specific), so there was nothing client-sensitive to filter when opening it up. Every mention of "admin-only" below reflects the original build, not the current state — see this note as the source of truth on access.

## Problem

Today there is no way for the admin/founder to see, at a glance, how much capital the platform's recommendation flow actually requires and how it's performing over a calendar month. `recommended_trades` (backend/db/init_db.py, `docs/schema.md`) already carries per-trade margin and P&L-relevant data, and Dashboard.jsx's "Recommended Positions" panel shows live per-trade margin/P&L — but there is no monthly rollup: how many recommendations were opened, how much margin was in use at any given point, and how much realized P&L was booked, are all things the admin currently has to reconstruct by scrolling and adding up individual cards by hand. This is invite-only, admin-facing capital-planning information, not a client-facing feature.

## Goal

An admin-only, in-app screen that, for any given IST calendar month (defaulting to the current, still-in-progress month), shows:

- Total number of recommendation positions entered that month.
- **Peak margin used** — the single highest point the margin-in-use figure reaches during the month — plus a day-by-day chart of margin-in-use across the month.
- Realized P&L booked during the month, plus a chart of how it accrued as positions exited.

The report is always computed live, directly from `recommended_trades`/`trade_legs`, for whatever month (complete or in-progress) the admin is currently viewing — there is no month-end "publish" step, no batch job, and no precomputed snapshot table. Viewing "this month" right now shows real numbers as of right now; viewing a past month runs the exact same query with different date bounds.

## Non-goals (v1)

- No PDF export, no email delivery — this codebase has no export/transactional-email infrastructure today (confirmed: no PDF library, no outbound-email sender anywhere in `backend/`), and the founder explicitly wants in-app only.
- No client-facing version of this report — admin-only (`require_role(super_admin, admin)`), same gate as every other `/profile/*` admin screen.
- No cross-month comparison view (e.g. month-over-month delta charts).
- No per-symbol / per-risk-level / per-trigger breakdown — the report is an aggregate across all `recommended_trades`, not segmented. (Segmentation is a plausible v2 — `risk_level`, `segment` via `_compute_segment()`, and `trigger_name` all already exist as columns/derived fields that a future version could group by.)
- No handling of `account_trades` (client brokerage positions) — this report is entirely about the admin-authored recommendation book, not what individual clients actually hold.
- No backfill/reconstruction of `margin_at_entry` for historical rows that predate this feature's migration (see Data model section) — those rows will show `NULL`/excluded-from-sum margin for any month that includes them.

## Data model change required

**This is a real gap, not a hypothetical one.** `recommended_trades.margin_required`/`margin_final` (`docs/schema.md`) are not immutable "entry" values — they get overwritten in place on an already-open row by `recalculate_recommendation_margin()` (`backend/live/manual_trade.py:401-441`, `UPDATE recommended_trades SET margin_required=?, margin_final=? WHERE id=?`, `manual_trade.py:434-437`). Confirmed call sites:

1. `POST /api/recommendations/<id>/adjust` (`backend/server.py:623-656`) — an admin can add/modify legs on an **open** trade via `/adjust`; on success it calls `recalculate_recommendation_margin(rec_id)` (`server.py:650-651`) against the **same row**, recomputing margin from the trade's *current* live legs (`get_current_legs()`) and overwriting `margin_required`/`margin_final` in place. Any admin adjustment to an open recommendation permanently loses that row's original entry-time margin.
2. `backend/live/triggers.py:588-592` — the NIFTY 500-multi auto-roll path (`_roll_forward`) creates a **new** `recommended_trades` row via `roll_recommended_trade()` (which does not accept/set margin at insert — see `queries.py:1804-1852`), then immediately calls `recalculate_recommendation_margin(new_trade_id)` to populate that fresh row's margin for the first time. This call is a legitimate "set the entry margin" operation for the new row, not an overwrite of a previously-captured value — but it uses the same function as (1), so the fix has to distinguish first-population from later-overwrite.
3. `backend/scripts/backfill_rolled_trade_margins.py` — a one-off backfill script that also calls `recalculate_recommendation_margin()` per rolled trade; same overwrite semantics, out of scope to change but worth being aware it exists.

**Fix:** add a new immutable column, `margin_at_entry`, and change exactly one function's write behavior:

- New column: `recommended_trades.margin_at_entry REAL`, nullable — added the same way every other optional column on this table was (`backend/db/init_db.py:406-414`'s `existing_cols`/`ALTER TABLE` loop): `("margin_at_entry", "ALTER TABLE recommended_trades ADD COLUMN margin_at_entry REAL")`. Mirrors `margin_final`'s semantics (the value Dashboard.jsx actually surfaces to users as "Margin" — `frontend/src/screens/Dashboard.jsx:381-385`), captured once, never recalculated.
- `open_recommended_trade()` (`backend/db/queries.py:381-407`): add a `margin_at_entry: float | None = None` parameter, include it in the `INSERT`.
- `add_manual_trade()` (`backend/live/manual_trade.py:140-152`) and the NIFTY 500-multi entry path (`backend/live/triggers.py:431-437`) — both already compute `margin_final` at entry time before calling `open_recommended_trade()`; both call sites should pass `margin_at_entry=margin_final` alongside the existing `margin_required=`/`margin_final=` kwargs.
- `recalculate_recommendation_margin()` (`backend/live/manual_trade.py:401-441`): change the `UPDATE` (currently `manual_trade.py:434-437`) to also set `margin_at_entry = COALESCE(margin_at_entry, ?)` (passing the freshly computed `margin_final`). This means:
  - A rolled trade's brand-new row (margin starts `NULL`, per `roll_recommended_trade()`) gets `margin_at_entry` populated on the very first call — the one that immediately follows row creation at `triggers.py:589-592` — behaving exactly like an entry-time capture.
  - Any *later* call against an already-populated row (i.e. every `/adjust`-triggered call in practice, since by the time an admin adjusts a trade it already has an entry margin) leaves `margin_at_entry` untouched, while `margin_required`/`margin_final` continue to be overwritten as before (needed — Dashboard's live "Margin" stat and other current-state UI genuinely want the freshest number, only the monthly report needs the frozen one).

No other read paths change. `margin_required`/`margin_final` keep their exact current behavior and every existing caller (Dashboard.jsx, `/api/recommendations`) is unaffected. Rows created before this migration ships will have `margin_at_entry IS NULL` forever (no reconstruction is possible — the pre-migration overwrite already happened, if it happened) — any month whose report includes such a row will simply treat its margin contribution as 0/excluded; call this out as a known, permanent data gap for pre-migration history rather than something to solve for.

## Mechanics / behavior

### "Month" always means "1st of the month through now-or-month-end, whichever is earlier"

Per the founder: this is never a finalized/frozen period, including for the current month. A requested month `YYYY-MM` (IST calendar month) resolves to:

```
month_start_utc          = IST midnight of the 1st  = UTC (day 1, 00:00) − 5h30m   # same pattern as get_today_closed_trades, queries.py:548-550
next_month_start_utc     = IST midnight of the 1st of the following month, same formula
effective_end_utc        = min(next_month_start_utc, datetime.now(timezone.utc))
```

`effective_end_utc` is the one piece of logic that makes "current month" and "past month" the same code path: for any month strictly in the past, `next_month_start_utc <= now_utc` already, so `effective_end_utc == next_month_start_utc` (the real month boundary) automatically; for the current, still-running month, it caps at "now" without any special-casing. All three metrics below use `[month_start_utc, effective_end_utc)` as their bound — half-open, UTC, computed once per request from the requested `YYYY-MM`. A requested month whose `month_start_utc` is in the future (nothing entered yet) should return zeroed/empty results, not an error.

`entry_time`/`exit_time` are stored UTC (`docs/schema.md`); this boundary computation is what prevents a trade entered at, say, 23:45 IST on the 31st (18:15 UTC on the 31st — still the 31st in UTC too, so this particular example wouldn't actually misfire) — but the general risk is real for late-evening IST entries near a UTC day boundary, which is exactly why the boundary must be computed via the UTC-minus-5:30 offset above and never by string-slicing the UTC timestamp's own date component.

### 1. Positions entered this month

```sql
SELECT COUNT(*) FROM recommended_trades
WHERE entry_time >= :month_start_utc AND entry_time < :effective_end_utc
```

Note: a monthly-expiry auto-roll (`triggers.py`'s `_roll_forward`, `roll_recommended_trade()`) closes the old row and opens a **new** `recommended_trades` row (`parent_trade_id` links them). Under this count, a roll that happens to land inside the reporting month counts as a newly "entered" position, distinct from its predecessor — consistent with how the rest of the schema already treats a roll (new header row, new `status='open'` lifecycle), but flagged explicitly since it means "positions entered" isn't purely "brand-new recommendations," it also includes roll-continuations. See Open Questions, and the "New vs Carried, added 2026-08-31" entry under Decisions for the separate `new_position_count`/`carried_position_count` split added later — same underlying rule (a roll counts as new when it happened this month), different population (all of `margin_positions`, not a date range).

### 2. Margin — day-by-day series + peak

Margin is **not cumulative** — it reflects net currently-open exposure at each point in time; a position's margin is released back to reusable capital the moment it exits. The day-by-day series must be a fluctuating step function (entries push it up, exits pull it down), and the headline stat is the **peak** of that series, not a sum — this is the number that answers "what's the minimum capital needed to run every recommended position at 1-lot sizing without ever being margin-constrained."

**Carry-forward rule (locked):** a position entered in an earlier month that is still `status='open'` continues to count toward every subsequent month's margin-blocked figure, using its `margin_at_entry` value, until its actual exit month — never a recalculated/current value.

Definition, for IST calendar day `d`: a `recommended_trades` row contributes its `margin_at_entry` to day `d`'s total if `entry_date_ist(row) <= d` AND (`row.status == 'open'` OR `exit_date_ist(row) >= d`) — i.e. a row blocks margin from its entry date through its exit date inclusive (it was live for at least part of the exit day). Rows with `margin_at_entry IS NULL` contribute 0 (pre-migration rows, or a trade whose entry-time SPAN margin fetch failed — `manual_trade.py`'s `get_margin()` call is already best-effort/try-except, so `NULL` margin on a live row is an existing, not new, possibility).

**Roll-day exception, added 2026-08-31:** the inclusive-exit-day rule above double-counts a same-day roll — `roll_recommended_trade()` stamps the old row's `exit_time` and its replacement's `entry_time` with the exact same instant (`db/queries.py`'s "atomically close old_trade_id ... open replacement" — see that function's own docstring), so the old row was never live at the same moment as its replacement, not even briefly, yet both intervals cover that one calendar day under the rule above, inflating that single day (and therefore `peak_margin_used` if it lands on the peak day) by the old row's full margin. Fix: when a row's `exit_date` equals its rollover child's `entry_date` (i.e. this exact same-instant-roll case, detected via `parent_trade_id`), treat that row's exit as **exclusive** for margin-series purposes only — it stops contributing on its exit day instead of through it, and the child picks up the day instead. This is a narrow carve-out, not a reversal of the inclusive-exit-day rule: a normal exit with no same-day rollover child (the common case) is unaffected and still counts through its exit day as originally locked above.

Implementation shape (avoid N per-day queries): one query fetches every row that could possibly overlap the requested month's day range —

```sql
SELECT id, entry_time, exit_time, status, margin_at_entry
FROM recommended_trades
WHERE entry_time < :effective_end_utc
  AND (status = 'open' OR exit_time >= :month_start_utc)
```

— then, in Python, walk each IST calendar day from the 1st through `min(last day of month, today)` and sum `margin_at_entry` for every fetched row whose `[entry_date, exit_date-or-open]` interval covers that day. Response includes both the full day-by-day series (for the chart) and its max (`peak_margin_used`, the headline stat).

### 3. Realized P&L — per-exit series + month total

Only trades that **exited** during the month count: `status = 'exited' AND exit_time >= :month_start_utc AND exit_time < :effective_end_utc`.

For each such trade, compute realized P&L using the **instrument-key-matching** method already used by `RecItem` on Dashboard.jsx (`frontend/src/screens/Dashboard.jsx:292-311`), **not** the positional `zip()` version currently used by `GET /api/recommendations` (`backend/server.py:540-553`, `zip(entry_legs, exit_legs)`). The frontend's own code comment (`Dashboard.jsx:292-296`) flags exactly why the backend's positional version can silently mis-pair legs: `get_current_legs()`/leg ordering can leave fewer exit rows than the flattened original+adjustment entry rows when an adjustment shares an instrument with the original entry, and pairing by array position rather than `instrument_key` then skips or misattributes P&L for that leg. Do not copy `server.py`'s `zip()` approach into the new monthly query — use the matching-by-`instrument_key` method instead:

- `entry_legs` = every `trade_legs` row for the trade with `action = 'entry'` (original entry, `adjustment_id IS NULL`, plus any adjustment-added entry legs) — i.e. `get_trade_legs(trade_id)` filtered to `action='entry'`.
- `exit_legs` = every row with `action = 'exit'`.
- For each entry leg `e`, find the exit leg `x` with the same `instrument_key` (skip if either price is `NULL`); `qty = e.lots * (e.lot_size or 1)`; contribute `(e.price - x.price) * qty` if `e.side == 'SELL'` else `(x.price - e.price) * qty`.
- Sum across all matched legs → that trade's realized P&L for the month.

Response includes each exiting trade's `(exit_date_ist, trade_id, realized_pnl)` (for a per-exit or cumulative chart — see Open Questions on chart form) and the month's total realized P&L (sum across all exits in range).

## Architecture impact

### Backend

- **Migration** — `backend/db/init_db.py`: add `margin_at_entry` to the `recommended_trades` `existing_cols` ALTER-TABLE loop (~`init_db.py:406-414`), same pattern as `margin_required`/`margin_final`/`display_code`/`note`/`risk_level`. Idempotent, runs on every startup, no separate migration tooling needed (per this codebase's existing convention).
- **`backend/db/queries.py`**:
  - `open_recommended_trade()` (`queries.py:381-407`): add `margin_at_entry` param + column to the `INSERT`.
  - New function, e.g. `get_monthly_report(year: int, month: int) -> dict`, implementing the three metrics above (positions-entered count, day-by-day margin series + peak, realized-P&L-per-exit + total) in one function — this is the only new SQL entry point needed; keep it in `queries.py` per this file being "the only file with SQL" (`backend/CLAUDE.md`).
- **`backend/live/manual_trade.py`**:
  - `add_manual_trade()` (`manual_trade.py:140-152`): pass `margin_at_entry=margin_final` to `open_recommended_trade()`.
  - `recalculate_recommendation_margin()` (`manual_trade.py:401-441`): change the `UPDATE` to `COALESCE`-preserve `margin_at_entry` as described above.
- **`backend/live/triggers.py`**: entry path (`triggers.py:431-437`) passes `margin_at_entry=margin_final` alongside existing margin kwargs.
- **New route** — `backend/server.py`, e.g. `GET /api/reports/monthly?month=YYYY-MM` (default: current IST month if omitted), `@require_role("super_admin", "admin")` — same gating pattern as every other admin-only route (e.g. `GET /api/users`, `GET /api/subscriptions`, `docs/apis.md`). Delegates straight to `get_monthly_report()`, converts the day-by-day series and per-exit list timestamps to IST-display strings the same way `_ist_str()` (`server.py:134-142`) already does elsewhere, and returns something like:

```json
{
  "ok": true,
  "month": "2026-08",
  "positions_entered": 14,
  "peak_margin_used": 812340,
  "margin_series": [{ "date": "2026-08-01", "margin": 620000 }, ...],
  "realized_pnl_total": 45210,
  "pnl_events": [{ "exit_date": "2026-08-06", "trade_id": 231, "realized_pnl": 12500 }, ...]
}
```

  (Exact field names/shape are an implementation detail for whoever builds this — the point is one endpoint returns everything the screen needs in one round trip, no separate calls per metric.)

### Frontend

- **New screen**, `frontend/src/screens/profile/Reports.jsx` — follows the exact convention of every other admin-only `/profile/*` screen (`Plans.jsx`, `Users.jsx`, `Subscriptions.jsx`, `Brokers.jsx`): self-guards with `if (!isAdmin) return <Navigate to="/profile" replace />` (`Plans.jsx:27`), uses `<PageHeader title="..." fallback="/profile" />` (`Plans.jsx:56`), colocated in `Profile.css` or its own `Reports.css` per the "no CSS framework, colocated `.css`" convention (`frontend/CLAUDE.md`).
- **Route**: add `<Route path="/profile/reports" element={<Reports />} />` to `frontend/src/App.jsx` (alongside the other `/profile/*` routes, `App.jsx:79-81`), lazy-loaded like every other screen (`App.jsx:19-33`).
- **Nav entry**: add a `MenuRow` under the existing "Admin" section of `frontend/src/screens/profile/ProfileHub.jsx` (`ProfileHub.jsx:57-65`), alongside Brokers/Users/Plans/Subscriptions — this is the established home for admin-only screens; there is no separate "admin section" outside `/profile/*` to create.
- **Data fetching**: new hook (e.g. `useMonthlyReport(month)` in `frontend/src/hooks/useTrades.js` or a new `hooks/useReports.js`), TanStack Query per this codebase's "no manual fetch/useEffect for data" rule (`frontend/CLAUDE.md`), query key `['monthly-report', month]`.
- **Month navigation**: default to the current IST month on load (server-side default via omitted `?month=`, or client computes current `YYYY-MM` in `Asia/Kolkata`). Light back/forward month arrows (± one month) rather than a full history dropdown/date-picker — there's no prior art in this codebase for a month-picker, and the founder's framing ("this month" as the live default, not a list of finalized snapshots) fits a simple prev/next affordance better than a dropdown. See Open Questions.
- **Summary numbers**: "Positions entered" and "Peak margin used" as headline stats (`fmtRs()`/plain integer via `frontend/src/utils/format.js`), same visual language as the existing `rec-stat`/`rec-stats-strip` pattern on Dashboard.jsx (`Dashboard.jsx:379-394`) — reuse that CSS class naming convention for consistency rather than inventing new stat-card styling.
- **Charts**: two — margin-blocked-per-day (step/line or area, showing the fluctuating carry-forward-aware series) and realized-P&L-over-the-month (see Open Questions for cumulative-vs-per-exit form). `frontend/package.json` has **no charting library** today (checked: no recharts/chart.js/victory/d3/visx among dependencies). This is an open decision — see below.

## Data / storage

- One new column: `recommended_trades.margin_at_entry REAL` (nullable), per the Data model section above. No new tables, no new retention job — this report is computed on demand from existing `recommended_trades`/`trade_legs`, nothing is persisted by the report itself (no snapshot table, per the founder's explicit "no batch job / no publish step" requirement).
- Existing `recommended_trades` rows (pre-migration) keep `margin_at_entry = NULL` permanently; already covered under Mechanics/Data model.

## Success criteria

- Manually cross-check `get_monthly_report()`'s "positions entered" count for a real past month against `SELECT COUNT(*) FROM recommended_trades WHERE entry_time >= ... AND entry_time < ...` run directly against `backend/data/drishti.db` for the same IST month bounds — must match exactly.
- Pick one `recommended_trades` row known to have entered in month M and still be `status='open'` at the start of month M+1: confirm `get_monthly_report()` for month M+1 includes that row's `margin_at_entry` in every day of M+1's margin series up through either its actual exit day or month M+1's end (whichever is earlier) — this is the carry-forward rule's concrete test.
- `peak_margin_used` for a given month equals `max()` of that month's own `margin_series` values — not a sum, not the last value.
- For a trade that both entered and exited within the same month, its `margin_at_entry` contributes to the margin series only between its entry and exit dates (inclusive), and it appears exactly once in `pnl_events` on its exit date, with `realized_pnl` matching what `RecItem` on Dashboard.jsx computes for that same trade (`Dashboard.jsx:298-311`) — cross-check the two numbers directly for a handful of real exited trades.
- Viewing the current, in-progress month before any admin action today still returns non-empty, accurate `positions_entered`/`peak_margin_used`/`realized_pnl_total` reflecting everything up to "now" — no field is `null`/stale/"pending publish."
- `GET /api/reports/monthly` returns `403` for a `client`-role session and `200` for `admin`/`super_admin`, matching every other admin-gated route.

## Decisions (confirmed by founder — locked, do not re-litigate)

- **"Positions entered" and monthly auto-rolls**: count every row including roll-continuations (rows with a non-null `parent_trade_id`) — matches how the schema already treats a roll as a new header row with its own lifecycle. No exclusion logic needed in `get_monthly_report()`'s count query.
- **New vs Carried, added 2026-08-31 (revised same day)**: the Reports UI (`Reports.jsx`) and Dashboard summary (`MonthSummaryCard.jsx`) both surface a New/Carried breakdown as small chips/pills. Two *different* fields exist for this, on purpose, and must not be conflated:
  - `positions_entered` (unchanged, above) — a pure date-range count, rolls included, used by `MonthSummaryCard.jsx`'s "X new this month" pill (time-scoped label, so it wants everything entered in-range, matching the locked decision above).
  - `new_position_count`/`carried_position_count` (new) — a *different* split, of `margin_positions` (not a date range): every row touching margin this month, partitioned purely by entry timing — `new_position_count` = entered this month, `carried_position_count` = entered an earlier month, still touching margin this month. `parent_trade_id` plays no role in this split at all. Used by `Reports.jsx`'s New/Carried chip row. `new_position_count + carried_position_count == len(margin_positions)` always.
  - Both fields treat a rollover as "new" (in the `new_position_count` sense) whenever it happened this month, in the sense of "its own row, its own freshly-computed margin" — `parent_trade_id` is lineage tracking only, never a reason to exclude a row from a "new" count. This design went through two wrong shapes before landing here, in the same day: (1) a `new_positions_entered` field that excluded rollovers entirely (violated the locked decision above outright); (2) a three-way `new_position_count`/`rolled_position_count`/`carried_position_count` split that gave rollover status its own dedicated bucket regardless of entry timing — rejected by the founder as unwanted complexity: "only two things, either its new for this month... [or it] enter[ed an] older month." A rollover from an earlier month lands in `carried_position_count` (not a separate "rolled" bucket) exactly like any other still-running older position; a rollover from this month lands in `new_position_count` exactly like any other fresh open. Read this section before touching either count again.
- **Chart form for realized P&L**: ~~a cumulative running-sum line across the month, with per-exit tooltips on hover (not separate per-exit bars/points as the primary form)~~ — **superseded 2026-08-30**: changed to a day-by-day net-booked bar chart (`PnlDailyBarChart`, `profile/ReportCharts.jsx`), green/red per day, matching the margin chart's own day-based x-axis. Reasoning: a connected/cumulative line implies continuous movement between exits that isn't real — there's no intraday price series behind it, only discrete exit events — so bars (no bar = no exit that day) are the honest representation given the data actually available.
- **Charting library**: hand-rolled SVG — no new dependency added to `frontend/package.json`. Both charts (margin step/area series, cumulative P&L line) are simple enough, bounded to a month's worth of points, to build directly.
- **Month-navigation UX**: prev/next arrows around the current month, not a dropdown/date-picker. Matches the "current month is the primary, live view" framing — no jump-to-any-month affordance in v1.
