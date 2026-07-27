---
name: calendar-spread-debit-proxy
description: Methodology for projecting NIFTY CE calendar-spread debit (sell-near/buy-far) forward in time and across spot moves, using rank0/rank1 expiry pairs in option_chain_5m as an empirical proxy — no fitted model needed. Use when asked to project, simulate, or estimate future calendar-spread debit, when picking a strike for the sell-near/buy-far CE strategy, or when extending docs/prd/calendar-spread-strike-scoring.md.
---

# Calendar-spread debit proxy — DTE-axis simulation

Data source: `option_chain_5m` (see `poller-data-flow` skill and `docs/prd/option-chain-capture.md` for how it's captured). This skill covers *analyzing* that table for the NIFTY CE sell-near/buy-far calendar spread specced in `docs/prd/calendar-spread-strike-scoring.md` — read that PRD for full strategy context before using this.

## The core trade

SELL the nearer weekly-cadence CE expiry, BUY the next one out, same strike. **Debit = far_leg_ltp − near_leg_ltp.** Net cost to open (or current value of) the spread.

## Expiry-pair resolution — merged cadence, not stored `expiry_rank`

Upstox tags each contract's `expiry_type` (`weekly`/`monthly`) itself — the monthly-coinciding date gets excluded from the `weekly` bucket even though it's calendar-wise 7 days after the prior weekly. Example actually observed: `weekly = [07-21, 08-04, 08-11]`, `monthly = [07-28, 08-25]` — all 7 days apart from each other, split across two buckets.

**Always derive the trade legs by merging and sorting real `expiry_date` values, never by trusting the stored `expiry_rank` column:**

```sql
SELECT DISTINCT expiry_date FROM option_chain_5m
WHERE symbol = 'NIFTY50' AND expiry_type IN ('weekly','monthly')
ORDER BY expiry_date
```

`cadence_dates[0]` = imminent/soon-to-expire contract (not traded). `cadence_dates[1]` = SELL leg. `cadence_dates[2]` = BUY leg. Always exactly 7 calendar days apart by construction.

## Implementation

`backend/analysis/calendar_spread_strike_scoring.py` — standalone CLI script implementing everything below. Run it rather than re-deriving ad hoc:

```bash
cd backend && source venv/bin/activate
python analysis/calendar_spread_strike_scoring.py --support 23800 --resistance 24500
```

Query helpers it relies on (in `backend/db/queries.py`): `get_merged_cadence_dates`, `get_option_chain_ltp`, `get_latest_option_chain_ts`, `get_option_chain_capture_days`.

## The DTE-proxy technique

**Key insight**: since every cadence step is 7 days, `cadence_dates[0]` vs `cadence_dates[1]` observed *today* is a live proxy for what `cadence_dates[1]` vs `cadence_dates[2]` (the actual trade) will look like once the SELL leg reaches whatever DTE `cadence_dates[0]` is at today.

**One DTE point is never a proxy — it's real.** `cadence_dates[1]` (the SELL leg) sits at some genuine DTE *today* (7 days, by construction of the 7-day cadence, as long as the imminent contract hasn't rolled yet). Today's actual `cadence_dates[1]`/`cadence_dates[2]` prices at that DTE are ground truth, not an estimate — don't proxy a DTE value that's already directly observable. Only *lower* DTE values (what the SELL leg will look like as it counts further down toward its own expiry) need the `cadence_dates[0]`-contract proxy described below. Compute the real DTE as `(cadence_dates[1] − today).days` and always include that point, sourced from the real legs, alongside the proxied lower-DTE points.

**The right mental axis is "DTE of the near leg," not "days from today."** A snapshot where some contract sits at `N` DTE proxies calendar date `sell_leg_expiry − N days` — regardless of which actual date that snapshot was captured on. Concretely: a snapshot taken when `cadence_dates[0]` had 1 DTE remaining proxies what the trade will look like when `cadence_dates[1]` has 1 DTE remaining (i.e. the day before it expires) — even though that snapshot itself was captured a week earlier than that target date.

```python
def get_ltp(expiry_date, strike, ts):
    # SELECT ltp FROM option_chain_5m WHERE symbol=? AND opt_type='CE'
    #   AND expiry_date=? AND strike=? AND ts=?
    ...

# proxy for "SELL leg at N DTE" using a snapshot where rank0 sat at N DTE:
near_dte_n = get_ltp(cadence_dates[0], strike, ts_when_rank0_was_at_N_dte)
far_leg    = get_ltp(cadence_dates[1], strike, ts_when_rank0_was_at_N_dte)
proxy_debit_at_N_dte = far_leg - near_dte_n
```

### Building the full decay curve

As daily captures accumulate, `cadence_dates[0]`'s contract counts down its own DTE day by day (6,5,4,3,2,1,0) before rolling to the next cycle. Each day of new capture backfills one more `(strike, DTE)` cell — no historical backfill is possible for DTE values not yet observed; they only arrive via ongoing capture. Check what's actually available before proxying:

```sql
SELECT DISTINCT ts FROM option_chain_5m
WHERE symbol='NIFTY50' AND expiry_date = ? -- the cadence_dates[0] contract
ORDER BY ts
```
then compute `DTE = (expiry_date - date(ts)).days` per distinct capture day to see which DTE cells exist.

**Validated example** (2026-07-21): only DTE=1 (from 2026-07-20 capture) and DTE=0 (from 2026-07-21 capture) existed. Strike 24250 proxy debit: 112.95 (1 DTE) → 116.25 (0 DTE), nearly flat. Strike 24600: 50.65 → 26.60, sharp collapse in the final day. Different strikes have materially different decay shapes right into expiry — this is the signal the strike-scoring PRD needs.

## Combining with a spot-fall scenario

Shift the strike by the assumed fall before doing the DTE-proxy lookup — a spot fall of `F` points makes strike `K` behave like today's `K + F` (further OTM relative to spot):

```python
def estimated_debit(strike, spot_fall_pts, dte_snapshot_ts):
    proxy_strike = round((strike + spot_fall_pts) / 50) * 50   # round to captured strike grid
    near = get_ltp(cadence_dates[0], proxy_strike, dte_snapshot_ts)
    far  = get_ltp(cadence_dates[1], proxy_strike, dte_snapshot_ts)
    return far - near if near is not None and far is not None else None
```

Run this across a grid of `(strike, spot_fall)` pairs to get a full sensitivity table — see `docs/prd/calendar-spread-strike-scoring.md`'s Mechanics section for the exact output shape (recommended strike + safe tolerance window).

## Ranking strikes — filter before ranking

**Never rank candidate strikes by worst-case loss alone.** A cheap, far-OTM strike can have the smallest *absolute* worst-case loss purely because there's so little premium in it to begin with — while also being a strike that already loses money in the flat-spot, no-time-passed case (thin legs decaying against each other with no edge). Filter to `no_move_ok` (P&L ≥ 0 at every available DTE with spot unchanged) **before** ranking by worst-case loss — otherwise the tool will recommend a structurally unsound strike just because it's cheap. Caught in testing: the naive rupee-loss-minimizing rank picked the most-OTM candidate, which was already `[LOSS]` on its own no-move projection.

## The diagonal collapse (not a bug)

In a multi-strike grid where rows are spot scenarios and columns are candidate strikes, the cell where `spot_level == K` (spot rallies to meet that exact strike) shows the **same projected debit across every column** — only the P&L differs (because entry cost differs per strike). This is because `proxy_strike = K + (entry_spot − scenario_spot)` reduces to `entry_spot` exactly when `scenario_spot == K`, regardless of K's value — every "spot rallies to become ATM at K" scenario collapses to today's actual ATM strike's debit. Expected, not an error; worth a one-line note in any grid output so it doesn't read as suspicious.

## Caveats

- This is a **first-pass empirical lookup, not a fitted model** — no regression, no smoothing. Values only exist at the exact `(strike, DTE)` cells actually captured; gaps between grid points aren't interpolated.
- Rounding a shifted strike to the nearest captured 50pt grid line introduces small error — acceptable for now, not validated at finer granularity.
- Assumes the current IV/vol-surface *shape* holds a week forward — a real assumption, not a fact, especially around events.
- Every table pulled this way is a **snapshot at one `ts`** — always report the `ts` and `spot_ltp` alongside any debit numbers so results are reproducible and comparable across pulls.
- Upside spot moves are out of scope for this strategy (see the PRD's non-goals) — this skill only needs to simulate downside falls.
