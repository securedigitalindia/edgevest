"""
Day-entry strategy definitions — the single source of truth for the Strategies
dashboard's "Day view" (docs/prd/strategy-day-view.md) AND for the shareable
artifact builder (analysis/strategy_viewer/). To add a strategy, add one entry.

A strategy is: an ENTRY RULE (when on a day we enter, and at which strike level)
+ LEGS (what is traded, relative to the entry strike) + VARIANTS (e.g. PE and CE
versions of one shape) + STRIKE OFFSETS (neighbouring entry strikes to compare).

Leg fields
  role     short name shown on the page ("Sell", "Buy")
  qty      signed lots: +n = buy n, -n = sell n.  net debit = sum(qty * price); P&L = debit_now - debit_at_entry
  opt      "{opt}" (the variant's own PE/CE) or a fixed "PE"/"CE"
  strike   offset in index points from the entry strike S — a number, or a dict per variant
  expiry   "M+k": monthly expiry k calendar months after the entry date's month (M+1 = next month, M+2 = month after)
  thin_oi  open interest below this is flagged as thin
Optional strategy field: dashboard=False keeps it out of the Strategies screen / its routes (artifact builder and
triggers still use it) — the day computation is heavy on prod, so new ones start artifact-only.
"""
DAY_STRATEGIES = {
    "diag_1x3_next_month": dict(
        label="Month Diagonal 1:3",
        description="Sell 1 option at the entry strike in next month's expiry; buy 3 options 1,000 points away in the month-after expiry. PE and CE.",
        summary=["PE + CE, independent", "Entry: first touch of a 100-multiple", "Sell 1 next month", "Buy 3 month after, 1,000 away", "No exit rule"],
        symbol="NIFTY50", lot=65,
        entry=dict(rule="touch", step=100, near=10),
        variants=["PE", "CE"],
        offs=list(range(-10, 11)),
        legs=[
            dict(role="Sell", qty=-1, opt="{opt}", strike=0, expiry="M+1", thin_oi=50000),
            dict(role="Buy", qty=3, opt="{opt}", strike=dict(PE=-1000, CE=1000), expiry="M+2", thin_oi=100000),
        ],
    ),
    "buy1_sell4_far": dict(
        label="Buy 1 / Sell 4 Far",
        description="Buy 1 option at the entry strike in next month's expiry; sell 4 options 2,000 points away in the month-after expiry. Usually a net credit; the 4 short far options carry large risk if NIFTY runs towards them.",
        summary=["PE + CE, independent", "Entry: first touch of a 100-multiple", "Buy 1 next month", "Sell 4 month after, 2,000 away", "No exit rule"],
        symbol="NIFTY50", lot=65,
        entry=dict(rule="touch", step=100, near=10),
        variants=["PE", "CE"],
        offs=list(range(-10, 11)),
        legs=[
            dict(role="Buy", qty=1, opt="{opt}", strike=0, expiry="M+1", thin_oi=50000),
            dict(role="Sell", qty=-4, opt="{opt}", strike=dict(PE=-2000, CE=2000), expiry="M+2", thin_oi=100000),
        ],
    ),
    "buy1_sell2_vertical": dict(
        dashboard=False,
        label="Buy 1 / Sell 2 Vertical",
        description="Buy 1 option 1,000 points away from the entry strike and sell 2 options 1,500 points away, both in next month's expiry (a ratio spread, no calendar leg). PE goes below the entry strike, CE above. The 2 short options carry large risk if NIFTY runs through the far strike.",
        summary=["PE + CE, independent", "Entry: first touch of a 100-multiple", "Buy 1 next month, 1,000 away", "Sell 2 next month, 1,500 away", "No exit rule"],
        symbol="NIFTY50", lot=65,
        entry=dict(rule="touch", step=100, near=10),
        variants=["PE", "CE"],
        offs=list(range(-10, 11)),
        legs=[
            dict(role="Buy", qty=1, opt="{opt}", strike=dict(PE=-1000, CE=1000), expiry="M+1", thin_oi=50000),
            dict(role="Sell", qty=-2, opt="{opt}", strike=dict(PE=-1500, CE=1500), expiry="M+1", thin_oi=50000),
        ],
    ),
}
