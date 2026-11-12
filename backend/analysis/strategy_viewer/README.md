# Strategy Day Viewer

A reusable, day-by-day performance viewer for option strategies on the locally stored NIFTY option chain
(`option_chain_5m` in `data/drishti.db`). One page, one chart: pick a **day**, a **variant** (PE/CE), an **entry strike**
and how many days **before / after** to look at. Add a strategy by adding a definition; the page does not change.

Published as a claude.ai Artifact (private): https://claude.ai/artifact/XCeo9sZFUCdEBUexL6ynUx

## Files

| File | Role |
|---|---|
| `strategies.py` | Re-exports the registry, which now lives in `backend/strategies/day_strategies.py` (shared with the dashboard's Day view; edit it there). |
| `build_data.py` | Thin wrapper over the shared engine `backend/strategies/day_view.py`: computes every day for one strategy, writes one JSON. The dashboard (`/profile/strategies/<id>`) and this artifact therefore always show the same numbers. |
| `template.html` | The page. Generic over any number of legs; contains no strategy logic. Placeholder `__DATA__` = list of strategy JSONs. |
| `build_page.py` | Fills `template.html` with one or more strategy JSONs -> a single HTML file to publish. |

## Use (from `backend/`)

```bash
venv/bin/python analysis/strategy_viewer/build_data.py diag_1x3_next_month /tmp/diag.json
venv/bin/python analysis/strategy_viewer/build_page.py /tmp/viewer.html /tmp/diag.json [/tmp/other.json ...]
# publish /tmp/viewer.html as an Artifact (same URL to update in place)
```

With more than one JSON the page shows a **Strategy** drop-down. The page limit is 16 MB; one strategy with 21 entry
strikes and both variants is about 6.8 MB, so 2 strategies fit. To fit more: fewer `offs`, fewer variants, or smaller `PRE/POST` in `build_data.py`.

## Adding a strategy

Add an entry to `DAY_STRATEGIES` in `backend/strategies/day_strategies.py` (it appears in both the dashboard and here):

```python
"my_strategy": dict(
    name="Shown in the drop-down", desc="One sentence shown on the page.",
    symbol="NIFTY50", lot=65,
    entry=dict(rule="touch", step=100, near=10),   # first touch of a multiple of `step`
    variants=["PE", "CE"],
    offs=list(range(-10, 11)),                     # compared entry strikes: level + off*step
    legs=[
        dict(role="Sell", qty=-1, opt="{opt}", strike=0, expiry="M+1", thin_oi=50000),
        dict(role="Buy",  qty=3,  opt="{opt}", strike=dict(PE=-1000, CE=1000), expiry="M+2", thin_oi=100000),
    ],
),
```

* `qty` is signed (+buy / -sell). Net debit = sum(qty x price). **P&L = debit now - debit at entry.** A 2-leg, 3-leg or 4-leg strategy works unchanged.
* `opt` = `"{opt}"` (the variant's own PE/CE) or a fixed `"PE"`/`"CE"` (for a PE+CE combo, use fixed types and one variant).
* `strike` is an offset in points from the entry strike; give a dict to differ per variant.
* `expiry` = `"M+k"`: the monthly expiry k calendar months after the entry date's month.

Then run the two commands above. If a strategy needs something the engine lacks, extend `backend/strategies/day_view.py`, not the template:

* **New entry rule** (e.g. fixed time of day, gap open, EMA cross): add a branch next to `_find_entry` in `day_view.py` that returns `(ti, L, kind)`: snapshot index, anchor level, and a short kind label.
* **Weekly expiries**: add a new `expiry` reference (e.g. `"W+1"`) in `compute_day()`'s `expiry()` helper.
* **Exit rules**: not modelled. Every strategy is marked to market with no exit (the page shows what the position did, not a closed trade).

## Output JSON (what the page reads)

`days[date]` = `{d, t, spot}` parallel arrays across the whole window (entry day plus 7 calendar days before / 30 after), `day0/day1` (index range of the entry day),
`touch` `{i, level, kind, spot, time}`, `exps` (resolved expiries per leg) and `V[variant][off]` = either `{A, skip: reason}` or `{A, j, lag, legs:[{role, qty, opt, strike, exp, px0, oi, st, px:[...]}]}`.
`px` is the leg's last-traded price at each snapshot (`null` = not quoted). `j` = entry snapshot; `lag` = minutes after the touch the entry was priced (waits up to 1 hour for a first trade).

## Data caveats (read before trusting a number)

* **Last-traded prices only** - no bid/ask. No brokerage, slippage or margin. NIFTY lot 65 is unverified.
* **Time steps:** entry day at 5 min, +-2 trading days at 15 min, the rest hourly (keeps the page small).
* **Missing prices come from the stored chain, not the page.** Each skipped entry shows its reason:
  * *expiry not in the stored chain* - the early chain (24 Aug - ~1 Sep) did not store the Sep 29 expiry, so Aug entries cannot be priced;
  * *strike has no trade yet (price 0)* - far-dated, far-from-spot strikes (e.g. Nov/Jan) are stored with price 0 until they trade;
  * *strike outside the stored strike range* - the chain keeps a window around spot.
  The Aug / early-Sep gaps could be filled from Upstox expired-contract history (not done; access unverified).
* Data covers 24 Aug 2026 onward (grows as the poller captures); entries in the last days have no "day after" yet.
* Verification used a stub-DOM Node run (no NaN/undefined/errors over every day x variant x strike x chart mode x window), plus a hand check of one debit. The page was not visually inspected in a browser from the session that built it.
