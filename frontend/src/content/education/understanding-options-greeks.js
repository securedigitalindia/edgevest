export default {
  slug: 'understanding-options-greeks',
  title: 'Option Greeks, in plain terms',
  category: 'fundamentals',
  summary: 'Delta, Theta, and Vega — the three you\'ll actually need, explained without the formulas.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'p', text: 'The "Greeks" are a set of numbers that describe how an option\'s price reacts to different things changing around it. There are more than three, but Delta, Theta, and Vega cover almost everything worth understanding as a starting point.' },

    { type: 'heading', text: 'Delta — sensitivity to the underlying\'s price' },
    { type: 'p', text: 'Delta measures how much an option\'s price moves for a 1-point move in the underlying. A deep ITM option has a Delta close to 1 (it moves almost point-for-point with the underlying, like owning the underlying itself would). A deep OTM option has a Delta close to 0 (a small move in the underlying barely affects it). An option exactly at the current price sits around 0.5 — this is also, loosely, the market\'s implied probability that the option finishes in the money.' },

    { type: 'heading', text: 'Theta — sensitivity to time' },
    { type: 'p', text: 'Theta measures how much value an option loses purely from one day passing, with everything else held constant — the daily "cost" of time decay described in "Why options exist." Theta is always working against an option buyer and in favor of an option seller: every day that passes, all else equal, the buyer\'s position is worth a little less and the seller\'s obligation is worth a little less to close out.' },

    { type: 'heading', text: 'Vega — sensitivity to volatility' },
    { type: 'p', text: 'Vega measures how much an option\'s price changes when the market\'s expectation of future volatility changes — not how much the underlying has actually moved, but how much movement the market now expects. Rising expected volatility raises option premiums (more uncertainty makes the "chance of a big move" more valuable); falling expected volatility lowers them, even if the underlying itself hasn\'t moved at all.' },

    { type: 'heading', text: 'Why this matters together, not one at a time' },
    { type: 'p', text: 'A real option position is being pulled by all of these at once — the underlying moving (Delta), a day passing (Theta), and volatility expectations shifting (Vega) all happen simultaneously. A position can lose money on a Delta move it "should" have profited from, if Theta or Vega worked hard enough against it that day. This is exactly why a position\'s price can look confusing without knowing which of these forces actually dominated.' },

    { type: 'callout', text: 'General options mechanics, not specific to any EdgeVest strategy or a recommendation about any particular position\'s Greeks.' },
  ],
}
