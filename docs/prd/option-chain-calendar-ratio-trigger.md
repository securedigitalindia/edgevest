# Option-chain triggers → draft trades (`NIFTY_CE_CAL_1X2`, `NIFTY_CE_ITM300_DIAG_1X2`, `NIFTY_CE_ITM400_DIAG_1X2`)

**Status:** built 2026-09-22. First triggers after all previous alert triggers were removed from `config.TRIGGERS` the same day (definitions in git history at `0912c0c`). Evaluated from live option-chain data; each fire creates a **draft trade only** — never an open trade, no margin until an admin publishes it from the Dashboard's Draft Strategies panel (`add_manual_trade(status="draft")`, same path as `strategy_cli.py create`). The draft itself sends no alert, but the **trigger fire** sends its own Telegram alert (below).

## Rule (as specified by the user)

- **Futures price:** the front-month NIFTY future's live LTP (Upstox `get_ltp`, one call per evaluation).
- **Strike K:** next `strike_step` (100) above the futures price for CE (`ceil`; PE would `floor`). Fut 23150 → CE K = 23200.
- **Legs (same strike K, both CE):** BUY `near_lots` (1) on the **near** expiry = nearest expiry with **DTE > 1**; SELL `far_lots` (2) on the **far** expiry = the next expiry after the near one.
- **Credit** = `far_lots × far_ltp − near_lots × near_ltp`, in premium points (not rupees), from the latest `option_chain_5m` snapshot.
- **Fires** when credit **> `min_credit_pts` (5)**. Sides: **CE only**. **One draft per side per IST day.**

(This section describes the first trigger. Two ITM diagonal variants follow below.)

## ITM diagonal variants (added 2026-09-22)

Two more entries on the same machinery (`type: "calendar_ratio_credit"`), each an independent trigger with its own once-per-day slot:

| Trigger | K1 — BUY 1 on near expiry | K2 — SELL 2 on far expiry | Fires when |
|---|---|---|---|
| `NIFTY_CE_ITM300_DIAG_1X2` | base − 300 | K1 + **400** | net **debit < 25** pts |
| `NIFTY_CE_ITM400_DIAG_1X2` | base − 400 | K1 + **400** | net **debit < 25** pts |

- `base` is the same "next 100 above the futures price" the first trigger uses (fut 23450 → base 23500 → ITM300: K1 23200 / K2 23600; ITM400: K1 23100 / K2 23500). The user's "300/400 points ITM" is measured from that base, not from the raw futures price.
- The user's "40 points gap" was confirmed as a **400-point** gap (`far_strike_offset: 400`). A 400 gap is what makes the debit threshold meaningful: on the 21 Sep close snapshot the debits were +56.25 (ITM300) and +47.65 (ITM400) — just above 25 — versus large credits with a 0 gap.
- "Debit under 25" means `near premium − 2 × far premium < 25` (config: `max_debit_pts: 25`; internally credit `2×far − near` > −25), so a net credit also qualifies. E.g. near 382.25, far 167.3 → 382.25 − 334.6 = 47.65 → not under 25 → no fire. Near expiry = nearest with DTE > 1, far = the next one after it (same as above). Drafts are noted `1:2 DIAG CE 23100/23500 (auto · debit 47.65)`.
- New config options: `itm_points` (K1 = base moved into the money), `far_strike_offset` (K2 = K1 moved out of the money). Both default to 0, which is the original same-strike calendar.
- Not fired on the last snapshot (debits 56 / 48 are above 25) — verified; a relaxed-threshold test produced the expected draft (BUY 23100 CE 29 Sep @382.25 / SELL 2x 23500 CE 6 Oct @167.3).

## Telegram alert on every fire (added 2026-09-22)

Every trigger that fires sends one Telegram message (`live/alert.py:send_chain_trigger_alert`, "🎯 Trigger Fired") from the same code path that creates the draft, so it goes out once per trigger per side per IST day — never per 5-min snapshot. Contents: trigger name, the setup note, both legs with lots/strike/expiry/price, net credit/debit, the rule that fired (`credit > 5` / `debit < 25`), the futures price, the chain snapshot time (IST), and an explicit **draft status**:
- **"Draft trade linked: #SEP26-16"** (+ Dashboard link when `FRONTEND_URL` is set) when the draft was created; or
- **"No draft trade linked"** with the error when draft creation failed. The fire claim is then released so the next snapshot retries; the failure alert is sent **once per trigger/side/day** (in-memory, resets on poller restart), retries are silent, and a successful retry sends the normal "linked" alert.

A failed Telegram send never affects the draft or the trigger loop. A trigger whose condition stays true after it has fired today sends nothing further.

## Mechanics

- `config.CHAIN_TRIGGERS` holds the definition; `live/chain_triggers.run_chain_triggers()` is called by `live/poller.py` right after each `option_chain_capture.run_capture()` (every 5 min, market hours only, wrapped in try/except so it can never crash the poll loop).
- Skips when the latest chain snapshot is older than 10 minutes (capture failure), fewer than two expiries qualify, or either leg has no traded price.
- Dedup: `chain_trigger_fires` (`UNIQUE(trigger_name, side, ist_date)`) — the fire is claimed *before* the draft is created and released if creation fails. A discarded or published draft does not free the day's slot.
- Draft: note `1:2 CAL CE <K> (auto · credit <n>)`, `risk_level: high` (net short far leg), leg prices = the snapshot LTPs, `trigger_name` = `MANUAL` (drafts flow through `add_manual_trade`).
- Adding a side/trigger is a config change (`"sides": ["CE","PE"]`, or another `CHAIN_TRIGGERS` entry of type `calendar_ratio_credit`).

## Things to know

- **The threshold is almost always true.** A same-strike calendar with a 2x far leg collects a large credit — ~226 pts for CE and ~194 pts for PE on the 21 Sep close snapshot — so `> 5` fires on the first evaluation of the day (≈09:15–09:20 IST). Effectively "one draft per day at market open". Raise `min_credit_pts` if a real filter is wanted.
- Uncovered risk: the 1x near long only partly covers the 2x far short, and the two legs are on different expiries — no margin/max-loss is computed for a draft until publish.
- The near-leg exit/roll is manual — nothing here manages the position after publish.

## Deploy notes

Needs `python poller.py init` on prod (creates `chain_trigger_fires`) and a poller restart. A backend (`edgevest-web`) restart is not required for this feature itself.
