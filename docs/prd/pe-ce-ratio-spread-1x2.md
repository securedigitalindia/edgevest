# PE+CE 1:2 Calendar Ratio (second registered strategy)

**Status:** built 2026-09-22 as the second provider in the admin Strategies dashboard (`docs/prd/admin-strategies-dashboard.md`). Research/monitoring only — same non-goals as the first strategy: not a trading signal, not risk/margin-validated, admin-only.

## Definition

Two independent strategies (PE side and CE side, never summed into a real headline — the "Combined" tile is reference only), each a **1:2 calendar ratio** (corrected 2026-09-22 after the user clarified it is a calendar, not a single-expiry spread):

| Leg | PE side | CE side | Expiry |
|---|---|---|---|
| BUY 1x K (base) | K = floor(fut + gap_sign·initial_gap) to `strike_multiple` | K = ceil(...) — nearest OTM strike next to the futures price | **upcoming** expiry |
| SELL 2x K2 | K − `leg_gap` | K + `leg_gap` | the **next expiry after the upcoming one** |

- **Upcoming expiry** = the nearest expiry with **DTE > 2** at entry (user rule: "if entry is on Monday, upcoming will be DTE > 2" — so a Monday entry skips the next-day Tuesday expiry and uses the following week's; same for a Tuesday entry on expiry day). Far = the expiry right after it.
- `leg_gap` defaults to **0** = same strike on both expiries (a pure calendar). A non-zero `leg_gap` offsets only the 2x far leg's strike further OTM, making it a diagonal. Same signed `initial_gap` convention as the diagonal: 0 = nearest OTM, positive = further OTM, negative = toward/into ITM.
- Value = `l1 − 2·l2`; P&L (points) = value now − value at entry (a net credit at entry shows as a negative entry value); rupees = points × lot size. Strike fallback (nominal, then ±100) reuses the diagonal's `_priced_leg`.
- Direction (BUY the 1x near leg, SELL the 2x far leg) follows the diagonal's own legs 1–2; the user said "1:2 on calendar" without stating buy/sell — see Open questions.

## Schedule (one independent window per week)

- **Entry:** 09:30 IST on the selected weekday (`entry_weekday`, default `WED`). The futures price at the first tick at/after 09:30 picks K. A holiday on the chosen weekday skips that week.
- **Exit:** 15:00 IST on the first Monday strictly after the entry date — the previous trading day if that Monday is a holiday (e.g. Ganesh Chaturthi, Mon 14 Sep 2026 → exit Fri 11 Sep), and never later than the upcoming expiry's own date. This is the day before the near leg's Tuesday expiry. Fixed by the strategy definition, not a config field.
- **After exit:** the window keeps its data to the upcoming expiry's 15:30 settlement as the tagged "if held to settlement" reference (dashed line, second daily table), same as the diagonal's windows.

## Decisions made without explicit user input (revisit if wrong)

- **`leg_gap` default 0** (same strike) — "calendar" implies one strike; configurable if a diagonal offset is wanted.
- **Buy near 1x / sell far 2x** — mirrors the diagonal's legs 1–2; not stated by the user.
- **Single entry weekday**, not a multi-day set — "day selection" read as a picker.
- **Entry time fixed at 09:30 IST**, **default weekday Wednesday**.
- **Price source = front-month future via live Upstox per request**, same accepted cost as the diagonal.

## Implementation

- `backend/analysis/nifty_ratio_spread_1x2_backtest.py` — pure compute + a CLI (`--start-date`, `--entry-weekday`, …). Reuses `SIDE_CONFIG`/`_priced_leg` (averaging backtest), `chain_series` (via `_priced_leg`), and `build_merged_embed()` (merged artifact) so windows have the exact diagonal shape and the existing dashboard components render them unchanged.
- `backend/strategies/registry.py` — `pe_ce_ratio_spread_1x2` provider. `service.py` — `_run_pe_ce_ratio_spread_1x2_cached()`: each window is cached in `strategy_backtest_windows` only once local data has moved past its expiry date; the cache key folds in `entry_weekday`, `leg_gap`, `strike_multiple`, `initial_gap`, `side`.
- `frontend/src/screens/profile/Strategies.jsx` — provider-specific config form (weekday select, no trigger section), two-row leg table, "Positions" wording. Everything else (tiles, charts, daily tables) is shared with the diagonal.
- No new tables.

## First results (local capture, 2026-08-24 → 2026-09-21, defaults: leg_gap 0) — n = 4 weeks per weekday

Wednesday entry, realized points (held-to-expiry reference in brackets):

| Entry | PE | CE |
|---|---|---|
| Wed 26 Aug | −124.00 (−314.65) | +109.80 (+139.65) |
| Wed 2 Sep | +2.40 (−18.65) | +90.90 (+167.60) |
| Wed 9 Sep | −73.25 (−138.00) | +70.35 (+164.90) |
| Wed 16 Sep | +137.80 (+136.45) | −9.65 (−7.25) |

Sum: PE −57.05 / CE +261.40. Monday entry (3 settled weeks + 1 open) sums PE −407.40 / CE +418.70 — a different picture, i.e. very entry-day sensitive. n = 4 per side is nowhere near the ~30 bar; local option-chain history only starts 2026-08-24. Entries are net credits (~150–285 pts) with an uncovered short 2x far leg — no risk/margin computation exists here.

## Open questions

- Confirm the direction (BUY 1x near / SELL 2x far) and `leg_gap` 0 = same strike.
- Multi-day entry selection, if wanted.
- Margin / max-loss for the short 2x leg is not computed (same gap as the diagonal).
