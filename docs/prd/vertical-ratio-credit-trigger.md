# Vertical ratio credit trigger (`vertical_ratio_credit`)

Option-chain trigger that creates a **draft** trade (never a live one) when a same-expiry 1:2 vertical
ratio spread on NIFTY pays a large enough net credit. Added 2026-11-15 on top of the existing chain-trigger
framework (`live/chain_triggers.py`, `config.CHAIN_TRIGGERS`).

## Position (per side, evaluated every 5-min `option_chain_5m` snapshot)
- `E` = the 100-multiple nearest the snapshot's NIFTY **spot** (`MAX(spot_ltp)` of the snapshot — the Day-view/backtest
  convention; NOT the futures price the other chain triggers use).
- BUY 1 @ `E ∓ buy_points`, SELL 2 @ `E ∓ (buy_points + 500)`, both in **next calendar month's monthly/quarterly expiry**
  (never a weekly). PE strikes lie below `E`, CE above.
- `credit = 2·sell_ltp − 1·buy_ltp` (points; lot = 65 units).

## Rule
**Multi-fire (2026-11-17):** fires at every snapshot where `credit >= 15` **and** both legs' open interest `>= 50,000` (OI read at the same snapshot) — once per strike E and conviction tier per IST day (`chain_trigger_signals`): a new E (NIFTY moved) fires again, and so does a higher tier on the same E (note says "up from LOW"); a repeat or lower tier does not. Replaces the earlier one-per-side-per-day rule.

## Conviction (by credit at the moment of firing)
| Credit | Conviction |
|---|---|
| 15 to < 20 | LOW |
| 20 to < 25 | MEDIUM |
| ≥ 25 | HIGH |

Stored in the draft's **note** (`1:2 VERT PE 24400/23900 (auto · credit 53.6 · HIGH conviction)`) and shown in the
Telegram "Trigger Fired" alert. There is **no conviction column** (decision pending: note-only now; a column on
`recommended_trades` + a Drafts-panel field would need a prod migration and frontend work). The tier is fixed at the
first firing; a larger credit later the same day does not create a second draft.

## Triggers configured
`NIFTY_VERT_1X2_800_1300`, `NIFTY_VERT_1X2_900_1400`, `NIFTY_VERT_1X2_1000_1500` (PE and CE each), via
`config._vertical_ratio_trigger(name, buy_points, min_credit_pts=15, medium_credit_pts=20, high_credit_pts=25, min_oi=50000)`.
`risk_level` = "high" (the 2 short options carry a loss that keeps growing below the break-even).

## Evidence (stored chain 24 Aug → 11 Nov 2026; read with care)
Credit ≥ 15 entries, marked to market at the latest data (no exit rule, no costs, last-traded prices):
800/1300: 24 entries, 21 in profit, avg +17.1 pts, worst −13.8. 900/1400: 24, 22, +17.7, −2.7. 1000/1500: 22, 22, +17.9, +1.0.
Higher credit → higher average result in all three. Caveats: ~3 independent stretches, nothing has reached expiry, NIFTY
mostly rose, no deep fall in the sample. Closer combinations (500/1000 … 700/1200) had much larger losses and were not built.
Backtest replay of the live evaluator over real snapshots matched the analysis on 68 of 74 first-fire events; the 6 differences
come from the analysis fixing OI at the touch time while the trigger reads OI at the firing snapshot.

## Implementation notes
- `queries.get_chain_spot`, `get_chain_quote` (ltp + oi), `get_monthly_expiries` (GROUP BY on the type-expiry index, cached 10 min).
- The runner skips the Upstox futures fetch and the weekly+monthly merge for this type (`_NO_FUT_TYPES`).
- `alert.send_chain_trigger_alert(..., conviction=, spot_label=)` — optional args, other triggers unchanged.
- No schema change; poller restart required for a config change to take effect.
