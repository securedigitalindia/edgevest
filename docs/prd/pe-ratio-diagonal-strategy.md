# NIFTY PE Ratio Diagonal — Strategy Definition

**Status (2026-09-09):** strategy shape locked and mechanically verified live. Backtesting now runs as an automated, windowed, averaging-entry sweep (see "Averaging trigger + windowed backtest" below) rather than one manually-picked entry-date at a time — 3 independent windows tested so far, n=3 (nowhere near enough for a conclusion). A mirrored CE-side variant runs the same windows independently (see "CE-side mirror + merged PE+CE artifact" below): PE realized profitable in all 3 windows so far, CE realized a small loss in all 3 — two separate strategies, not summed into one traded position. Not yet risk-validated (see Open questions) and not yet a tracked/traded strategy — no `trade_suggestions.py` template, no `recommended_trades` row, no alert. The tooling that simulates/tracks this strategy is documented separately in `docs/prd/pe-ratio-diagonal-simulator.md`; this doc is about the **strategy itself** — what it is and why it's shaped this way — not the CLI/artifact built to study it.

## Problem

The user is evaluating a NIFTY PE ratio diagonal spread as a candidate strategy before trading it with real capital. The construction had been built up interactively (see conversation history and `docs/prd/pe-ratio-diagonal-simulator.md`'s own revision log) but existed only as CLI parameters, never written down as a strategy in its own right — its exact legs, its entry rule, and the reasoning behind its shape. This doc captures that definition once, so it can be referenced, questioned, and risk-checked independently of whatever tooling happens to simulate it.

## Core idea

A **put ratio diagonal**, laddered across three consecutive weekly expiries, built from two overlapping sub-structures:

1. **The front diagonal (legs 1+2)** — buy 1x a near-dated put, sell 2x a further-dated put 400 points lower. This is the original 2-leg shape this whole effort started from: the near leg buys some downside optionality; the 2x further-dated short leg finances it (usually leaving a small net debit, sometimes a credit) and harvests theta, at the cost of uncovered short exposure below the lower strike if NIFTY falls hard and stays there through the second leg's expiry.
2. **The rear ladder (legs 3+4), one expiry cycle further out** — sell 1x the *same* near strike K, but in expiry2 instead of expiry1 (a reverse calendar on K: buy the nearer contract, sell the further one, same strike), paired with buying 2x the lower strike (K-400) in expiry3 (which, together with leg 2's sale of the same K-400 strike in expiry2, forms a textbook long calendar spread — sell near, buy far, same strike — a standard theta/vol structure).

The two sub-structures share legs 2 and the K-400 strike, which is what makes this a single 4-leg position rather than two separate 2-leg trades. The practical effect: by the time expiry1's near leg has fully decayed (or expired), the position already has legs sitting in expiry2/expiry3 — legs 3+4 pre-stage the next diagonal cycle, so nothing has to be manually re-entered week over week. It reads as a **self-rolling version of the original 2-leg diagonal**, not a fundamentally different strategy.

*(This structural read — front diagonal + rear reverse-calendar/long-calendar pair — is this author's decomposition of the legs as specified, not a thesis the user separately stated. Flagging it as an interpretation to confirm, not a given.)*

## Strategy shape

```
LEG 1  BUY  1x   expiry1   strike K        PE
LEG 2  SELL 2x   expiry2   strike K-gap    PE
LEG 3  SELL 1x   expiry2   strike K        PE
LEG 4  BUY  2x   expiry3   strike K-gap    PE
```

- `gap` default **400** points (e.g. K=24200 → K-gap=23800). Not derived or optimized — given directly by the user.
- **K is not chosen by the trader.** Live execution rule: **at 09:30 IST on entry day**, snap the front-month NIFTY future's price down to the next-lower 100-multiple (e.g. fut=24065 → K=24000, fut=24204.3 → K=24200).
- **expiry1/2/3** are the first three expiries (merging Upstox's weekly+monthly buckets, sorted by real date) with **DTE > 1** relative to entry day — not just DTE != 0. The stricter-than-usual DTE>1 cutoff exists specifically because of the 09:30 execution rule: an expiry with only 1 day left is already too close to entry to serve as the near leg.
- Reference price is the **front-month NIFTY future's LTP**, never the index spot — see `nifty_fut_ref.py`'s docstring for why the two diverge and why the future is what a trader actually watches for this kind of entry.
- Lot size is resolved live from the futures contract (currently 65), never hardcoded.

## Payoff behavior — empirically observed, not modeled

No greeks/IV model backs this strategy; everything below is either a strike-shift proxy grid or a real historical replay, not a priced estimate.

- **Live spot-move grid** (2026-09-08 snapshot, K=23700/23300): gains as the future falls (+59.90 pts at fut-400), roughly flat near entry, turns negative as the future rises through +200/+300 (-29.75 / -43.60 pts) — i.e. within the simulated ±400 range, the position **favors a falling or flat future**, consistent with a net-short-premium, downside-friendly construction. (The grid showed an anomalous partial recovery at the +400 extreme, attributed to sparse proxy-strike data at that edge, not a real payoff feature — flagged, not resolved.)
- **Real 6-day entry-to-date track** (entry 2026-09-01, K=24200/23800): the future fell from 24204.3 to 23744.1 over the period, and the position gained continuously, +120.10 pts (+₹7,806.50 on a 65 lot) by 2026-09-08 (expiry1 at DTE=0). Directionally consistent with the grid's downside-favoring read — but this single real window mixes the future's actual drop together with time decay, so it does not isolate which effect (direction vs. theta) is doing the work.

Both runs are reproducible: `backend/analysis/nifty_pe_ratio_diagonal_simulator.py` (live grid) and `nifty_pe_ratio_diagonal_simulator_v2.py --entry-date 2026-09-01` (the tracked run), and viewable at the published artifact in `docs/prd/pe-ratio-diagonal-simulator.md`.

## Non-goals

- **No backtested win rate or statistical edge claim** — this is one live construction rule, verified on one real 6-day window and one live snapshot grid, not validated across historical regimes, volatility spikes, or expiry-week gap events.
- **No priced/greeks model** — no Black-Scholes, no IV surface. Every "what if price moves" number is an empirical strike-shift proxy (see the simulator PRD's Non-goals for the technique).
- **No margin/capital-requirement computation** — unlike this repo's ladder backtest tooling, nothing here calls a margin or brokerage API.
- **No claim that gap=400 or the 1:2:1:2 leg ratio is optimal** — both were specified directly by the user, not derived or swept over alternatives.
- **No execution path** — no `recommended_trades` row, no Telegram alert, no `trade_suggestions.py` template. Pure strategy definition + simulation/research.

## Backtest data capture (added 2026-09-08, revised same day)

Backtesting this strategy needs option premiums for whatever strikes/expiries each historical entry-date would have picked — but **Upstox's option-chain resolution (`get_put_call_option_chain`) only works for an expiry that hasn't settled yet**. Confirmed live: resolving strikes for 2026-08-25 (settled 2 weeks prior) returned zero rows, while the same call for 2026-09-08 worked right up until settlement that evening. This means **historical backfill is impossible** — there is no way to retroactively fetch a past cycle's contracts once they've settled, regardless of method. The only viable path is capturing data *before* each cycle settles, accumulating a real sample over many weeks/months.

**First attempt (built, then fully removed within the same session):** a narrow table (`pe_diagonal_backtest_ticks`) scoped to exactly this strategy's derived legs (K/K-gap across the 3 resolved expiries), written by a `--save-db` flag on v2. Captured 7 entry-dates (2026-08-31 through 2026-09-08, 2,135 ticks) on the last day the closing cycle was resolvable. **Rejected as the go-forward design**: it only stores the strikes *this one entry rule* picks — the moment a different entry trigger picks a different strike or gap, its needed premiums aren't in there, hitting the exact same "can't backfill after settlement" wall again for every new trigger variant. Initially kept (frozen, no writer) on the reasoning that its captured rows were irreplaceable — but a subsequent prod-DB pull overwrote the local SQLite file entirely, and since prod's own poller never created this table, those 2,135 rows were already gone by the time anyone checked. With nothing left to protect, the schema (`db/init_db.py`) and its two read-only query helpers (`db/queries.py`) were removed too — this table no longer exists anywhere, in code or data.

**Actual design**: capture the **raw full option chain** (every strike, CE+PE, across the near weekly+monthly expiries) every 5 minutes, and derive whichever strategy's specific legs are needed at *analysis* time, not at capture time — so any future entry trigger, whatever strikes it picks, is already covered. This is exactly what `option_chain_5m` + `live/option_chain_capture.py` already do; the only real gap was **uptime** (that capture only ran as part of the full live poller, which has had real gaps — confirmed stopped dead 2026-09-04, leaving only ~10 days of data total historically).

**Reverted same day.** A standalone capture loop (`live/chain_capture_loop.py`, `python poller.py capture-chain`) and a monthly-capture-drop (`EXPIRY_TYPES` narrowed to `["weekly"]`) were both built, then rolled back at the user's direction: the existing full poller (`poller.py live`) already runs this exact capture as part of its own loop, and the user's plan is to keep that running rather than add a second, separate capture mechanism. **Both changes fully reverted** — `option_chain_capture.py` and `poller.py` are back to their pre-2026-09-08 state, `chain_capture_loop.py` deleted. `option_chain_5m` still captures weekly+monthly as it always did, exclusively via the full live poller.

**Where this actually leaves backtest data capture**: relies entirely on the user keeping `poller.py live` running continuously (confirmed running against prod as of 2026-09-09) — no separate/parallel capture mechanism, per the revert above.

## Backtest correctness fixes (2026-09-09)

Two real bugs surfaced while actually running backtests against the local chain data, both from the same root cause: the capture's **weekly rank window** (originally 0-2, "the 3 nearest weekly-cadence expiries at capture time") doesn't always line up with what the strategy's own DTE>1 rule needs.

- **Root cause**: the strategy skips the imminent weekly expiry when its DTE<=1. If that skipped expiry is itself weekly-classified (not a month-end date, which Upstox buckets as "monthly" and which therefore doesn't consume a weekly rank), the strategy's 3 needed expiries land on capture ranks 1/2/3 — and rank 3 was never captured. Confirmed concretely: entering 2026-08-31 needs expiry3=2026-09-22, which is weekly rank 3 that day (Sep1 sits at rank 0 and gets skipped, Sep8/Sep15 are ranks 1/2). Whether this bites at all depends purely on calendar coincidence (is the skipped expiry month-end or not) — it hit Aug25-28 the "good" way (Aug25 itself was month-end, so no weekly rank was wasted skipping it) and Aug31/Sep1 the "bad" way.
- **Analysis-side fix**: `nifty_pe_ratio_diagonal_backtest.py`'s `chain_series()` now takes `backfill_from_ts` and falls back to a live Upstox pull to fill the gap when local coverage doesn't reach back far enough — works pre-settlement only. This was silently understating an entry's true debit by >2x before the fix (Aug31: reported 51.25, true 22.95) because the missing leg made the script think no data existed at all before Sep2, and it silently shifted the whole entry forward to whenever all 4 legs first overlapped.
- **Capture-side fix (the actual root-cause fix)**: `option_chain_capture.py`'s `EXPIRY_RANKS` widened from `[0,1,2]` to `[0,1,2,3,4]` — the DTE<=1 rule never skips more than one expiry, so rank 3 is the true requirement, rank 4 is headroom. Verified live: now captures 4 weekly expiries per snapshot (Sep8/15/22/Oct6) instead of 3. Closes this gap for good going forward; the analysis-side fallback remains as a safety net (e.g. for the transition period before rank-3 data has had time to accumulate, or any future strategy variant that reaches even deeper).

**A second, more severe instance of the same bug class (2026-09-09, same day)**: NIFTY's expiry calendar has a third Upstox type, **"quarterly"** — and near-term it isn't quarterly-spaced at all. `2026-09-29` (the natural next expiry after `2026-09-22`, only ~7 days later) is bucketed as `quarterly[0]`, not `monthly`. `get_merged_cadence_dates()` only ever read `weekly`+`monthly`, so `2026-09-29` was **entirely invisible** to expiry-triplet resolution — not a depth/rank problem this time, a missing-type problem. Resolving a 2026-09-07 entry's 3rd expiry silently jumped from `2026-09-22` straight to `2026-10-27` (`monthly[0]`, 50 days out) instead of the real ~22-day-out expiry, pricing the position against a far longer-dated, far more expensive contract — **entry debit was reported as 168.35 pts; the true value (once fixed) is 9.55 pts, off by more than 17x.** Fixed two ways: `get_merged_cadence_dates(symbol, include_quarterly=True)` — an opt-in parameter (defaults `False` to avoid silently changing `calendar_spread_strike_scoring.py`'s own weekly+monthly-only cadence indexing) — and `option_chain_capture.py`'s `EXPIRY_TYPES` now includes `"quarterly"`. All three PE-diagonal scripts (`nifty_pe_ratio_diagonal_backtest.py`, `_averaging_backtest.py`, `_simulator_v2.py`) now pass `include_quarterly=True`; v1 (`nifty_pe_ratio_diagonal_simulator.py`) needed no change since it reads every type Upstox returns directly, unfiltered. The Sep 7 artifact was republished with corrected numbers.

## Averaging trigger + windowed backtest (2026-09-09)

Extends the single-entry backtest with two layers, built up over the same session:

1. **Averaging/laddered entry** (`nifty_pe_ratio_diagonal_averaging_backtest.py`) — after a first entry, every time the future rises `--up-move` (default 100) points from the LAST triggered set's own entry price, a brand-new independent 4-leg set is entered — fresh expiry triplet resolved at THAT trigger's own date (not inherited from the first entry). Combined P&L = sum of every already-triggered set's own P&L since its own entry; once a set's near leg settles, its contribution freezes at its last known value rather than vanishing from the sum.
2. **Windowed backtest** (`nifty_pe_ratio_diagonal_windowed_backtest.py`) — chains the averaging backtest across every natural expiry-triplet window in a date range automatically, instead of the user picking each window's start date by hand. A new window begins on the first trading day whose own `resolve_expiry_triplet` gives a different expiry1 than the current window's (the same rollover point already governing every entry-date this project has tested). Each window is a **fully independent position** — own entry, own P&L, never summed into one continuous position.

**Exit timing**: a window's P&L (and its own averaging-trigger scanning) is bounded to end right when the NEXT window's entry happens — not whenever this window's own near leg actually settles (which can land after the next window has already begun; e.g. the Aug25 window's expiry1 settles Sep1, a day after the Aug31 window started — holding to real settlement would mean two overlapping windows in time). This matches a rolling weekly strategy that closes out and re-enters at each rollover.

**Post-exit reference view**: the data past that exit point isn't discarded — every window also reports what its P&L *would have been* had it been held to its own near leg's actual settlement instead, clearly separated from the realized figure (`realized_pnl_pts`/`exit_ts` = actually realized; `latest_pnl_pts` = the full unbounded "if held" comparison, tagged `post_exit` per tick). The artifact draws this as a dashed, muted chart continuation past a red "Exit" marker, plus a second, visibly faded daily table.

**Artifact**: one tabbed page, one tab per window — https://claude.ai/code/artifact/a087f925-cb3a-48f0-842e-6d625ff254b5. Built from `nifty_pe_ratio_diagonal_windows_template.html` (the static HTML/JS shell, `__DATA_PLACEHOLDER__` substituted at publish time) + `nifty_pe_ratio_diagonal_windows_artifact.py` (the one-command builder — runs the windowed backtest, reshapes each window into the template's JSON shape, writes the final publishable HTML). To refresh with more data:

```
cd backend && source venv/bin/activate
FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_windows_artifact.py \
    --start-date 2026-08-25 --output /tmp/windows_artifact.html
```

then publish `/tmp/windows_artifact.html` with the Artifact tool, passing `url` = the URL above, to update in place rather than create a new artifact.

**Results as of 2026-09-09** (3 windows tested, n=3 — nowhere near the ~30 needed for any real conclusion):

| Window | Sets | Realized P&L (at exit) | If held to actual settlement |
|---|---|---|---|
| 25 Aug (expiry1=Sep1) | 3 | +159.50 pts | +35.80 pts |
| 31 Aug (expiry1=Sep8) | 1 | +55.85 pts | +119.20 pts |
| 07 Sep (expiry1=Sep15) | 1 | still open, +24.20 pts so far | — |

Sum of realized: +239.55 pts (+₹15,570.75 on a 65 lot) — again, three independent trades' outcomes summed for reference, not a real portfolio return. Notably the exit-vs-hold comparison flips direction between the two settled windows (25 Aug: exiting early was better; 31 Aug: holding longer would have been better) — with n=2 that's not evidence either rule is generally right, just a reminder the rollover-exit choice has real, non-trivial impact worth continuing to track as more windows accumulate.

## CE-side mirror + merged PE+CE artifact (2026-09-09)

The same averaging/windowed backtest runs a **mirrored CE-side variant** of the strategy (`side="CE"` on `nifty_pe_ratio_diagonal_averaging_backtest.py`, `_windowed_backtest.py`, and `_windows_artifact.py`): K ceiled to the next 100-multiple (keeps the bought leg OTM upward, since calls gain on upside), K2=K+gap (further OTM upward), and averaging triggers fire on **down**-moves instead of up-moves — the user's explicit mirror-image choice, not derived. PE and CE are tracked as fully separate strategies sharing only the same window boundaries (symbol-wide expiry rollovers, not side-specific) — never summed into one traded position.

A CE-side-specific correctness fix was needed: a captured `ltp` of exactly `0` on a far-OTM, thinly-traded NIFTY CE (option-chain skew means CE strikes this far OTM see far less trading than equivalent-distance PE strikes) means "no trade yet," not "worthless" — treated as missing data (same as NULL) in `chain_series()` so timestamp intersection skips forward to genuine price discovery instead of pricing a leg at a false zero. Separately, the CE side fires more/later averaging sets than PE within the same window, which was letting a later set's own (later) expiry stretch the "if held to settlement" reference series past the window's actual settlement point — capped explicitly to the window's own `expiry1` settlement.

**Merged artifact**: `nifty_pe_ratio_diagonal_merged_windows_artifact.py` + `nifty_pe_ratio_diagonal_merged_windows_template.html` run PE and CE independently within the same windows and render both together — https://claude.ai/code/artifact/39795623-8515-475f-8515-afee86658aea. PE's and CE's own realized figures are the two primary stat tiles; a third "Combined (PE+CE)" tile/line/column is kept visually secondary (muted color, dashed line) — reference only, never the headline, since these are two independent strategies whose outcomes aren't actually a real portfolio return when added. Rebuild:

```
cd backend && source venv/bin/activate
FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_merged_windows_artifact.py \
    --start-date 2026-08-25 --output /tmp/merged_windows_artifact.html
```

then publish `/tmp/merged_windows_artifact.html` with the Artifact tool, passing `url` = the URL above, to update in place.

**Results as of 2026-09-09** (same 3 windows, n=3 per side):

| Window | PE realized | CE realized |
|---|---|---|
| 25 Aug | +159.50 pts | -20.70 pts |
| 31 Aug | +55.85 pts | -12.45 pts |
| 07 Sep (open) | +24.20 pts | -19.00 pts |

The single-side artifact (`nifty_pe_ratio_diagonal_windows_artifact.py`, PE-only URL above) and its template are untouched and still work for a focused single-side view — the merged builder is additive, not a replacement.

## Open questions / risks

- **Tail risk on a fast, large downside move before expiry2 is unquantified.** Leg 2 (SELL 2x K-gap PE, expiry2) is the position's main uncovered-short exposure; its designated "hedge," leg 4 (BUY 2x K-gap PE), sits in expiry3 — a *different* expiry with different time value, not the same contract. A sharp crash well below K-gap before expiry2 could hit leg 2 faster than leg 4 offsets it, since calendar-spread legs don't move point-for-point during a fast move even at the same strike. This has not been stress-tested.
- **No worst-case / max-loss computation** — the strike-shift proxy grid only covers ±400 points; nothing here establishes where the position's loss stops growing (or whether it's theoretically unbounded on one side).
- **No margin estimate** — unclear what capital this actually ties up given the short legs, independent of the premium P&L tracked so far.
- Whether/how this becomes a real tracked strategy (a `trade_suggestions.py` template, a `recommended_trades` row, a Telegram alert) is undecided — flagged for whoever picks this up next, same as the simulator PRD's own open question.
- **The exit-at-rollover rule itself is a design choice, not a validated one.** Exiting a window exactly when the next window's entry happens (rather than holding to the near leg's actual settlement) was the user's explicit choice, and mechanically it's now correct — but *whether that's the better rule* is unresolved. The two settled windows so far disagree on which is better (25 Aug: exit-early beat hold-to-settlement; 31 Aug: the reverse) — n=2 is nowhere near enough to say which pattern is real. Worth revisiting once more windows accumulate, using exactly the realized-vs-reference comparison the artifact already tracks.
- **Averaging (+100pt up-move) itself is unvalidated as a rule** — same status as the leg-gap/ratio: given directly, not derived. Whether a different threshold, or no averaging at all, performs better is untested.
