# Month diagonal 1:3 — debit-conviction trigger (`diagonal_debit_conviction`)

Option-chain trigger (framework: `live/chain_triggers.py`, `config.CHAIN_TRIGGERS`) that creates a **draft** trade for the
"Month Diagonal 1:3" day-entry strategy (`strategies/day_strategies.py` → `diag_1x3_next_month`). Added 2026-11-15.

## Position (per side, every 5-min `option_chain_5m` snapshot)
- `E` = 100-multiple nearest the snapshot's NIFTY **spot** (`MAX(spot_ltp)`; not the futures price).
- Candidate strikes `S` (step 100): **PE** `E+200 … E−500` (ITM 200 → OTM 500), **CE** `E−200 … E+500`.
- For each `S`: **SELL 1 @ S** in next calendar month's expiry (M+1) and **BUY 3 @ S∓1000** in the month after (M+2) (PE below, CE above).
  Monthly/quarterly expiries only, never weeklies.
- `debit = 3·far_ltp − 1·near_ltp` (points; negative = net credit).
- Liquidity: near-leg OI ≥ 50,000 and far-leg OI ≥ 100,000 (the Day view's "thin" thresholds), read at the same snapshot.

## Rule
At each snapshot the **lowest liquid debit across the strike range** wins. Fire if it is **< 200**, once per trigger per side per
IST day (`chain_trigger_fires`). The strike is whichever had the lowest debit at the first snapshot that met the rule.

## Conviction (by that debit)
| Debit | Conviction |
|---|---|
| < 120 (incl. any net credit) | HIGH |
| 120 to < 180 | MEDIUM |
| 180 to < 200 | LOW |

Stored in the draft note (`1:3 DIAG PE 25000/24000 (auto · debit 195.2 · LOW conviction)`) and in the Telegram "Trigger Fired"
alert. No conviction column exists. The tier is fixed at the first firing.

## Triggers configured
Quantities are signed (+buy / −sell), `debit = near_qty·near_ltp + far_qty·far_ltp`, and conviction tiers are debit thresholds, so a
credit rule is written with negative numbers. Both use `config._diagonal_debit_trigger(...)`, PE + CE, `risk_level` = "high":
- `NIFTY_DIAG_1X3_1000` — `near_qty=-1, far_qty=3, far_offset=1000`; fires on debit < 200 (HIGH < 120, MEDIUM < 180, LOW < 200).
- `NIFTY_B1S4_FAR_2000` — Buy 1 / Sell 4 Far (`buy1_sell4_far`): `near_qty=1, far_qty=-4, far_offset=2000`; fires on a **credit** > 25
  (`max_debit_pts=-25`): LOW credit 25–50, MEDIUM 50–75, HIGH 75+ (`medium_below=-50, high_below=-75`). Same ITM 200 … OTM 500 scan,
  same liquidity guard. On the stored chain it would have fired 19 times, all PE: October 13 (12 LOW, 1 MEDIUM), November 6 (2 LOW, 3 MEDIUM,
  1 HIGH); never CE, never in September. No performance backtest run.

## What the stored chain says (24 Aug → 11 Nov 2026) — read with care
Replaying the live evaluator over 48 stored days: 95 fires (94 expected from the independent analysis; 92 identical on time, strike
and debit, 3 differ by an OI-at-snapshot vs OI-at-touch difference). **It fires on almost every day on both sides**, mostly at the
09:20 snapshot. By conviction: HIGH 46, MEDIUM 33, LOW 16. September was nearly all HIGH (debits ~25–130); October and November
mostly MEDIUM/LOW (debits ~135–195) — so the tier mostly reflects the month's expiry/volatility regime, not a daily signal.
**No P&L / performance backtest has been run for this strategy with these thresholds.**

## Implementation notes
Shares `queries.get_chain_spot/get_chain_quote/get_monthly_expiries` and the no-futures-fetch path (`_NO_FUT_TYPES`) with
`vertical_ratio_credit` (`docs/prd/vertical-ratio-credit-trigger.md`). No schema change; poller restart required.
