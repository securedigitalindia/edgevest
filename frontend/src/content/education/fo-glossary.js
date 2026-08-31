export default {
  slug: 'fo-glossary',
  title: 'F&O terms used on EdgeVest',
  category: 'numbers',
  summary: 'Lot, strike, expiry, CE/PE, ITM/OTM, leg, roll — the words you\'ll see on every trade card, explained once.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'p', text: 'Every recommendation on the Trades and Positions screens is built from a small set of recurring terms. This page explains them once, in plain language, so the other Learn articles (and the app itself) don\'t have to keep re-explaining them.' },

    { type: 'heading', text: 'The basics' },
    { type: 'table',
      headers: ['Term', 'Meaning'],
      rows: [
        ['Futures (FUT)', 'A contract to buy or sell an index/stock at a fixed price on a future expiry date. Its value moves almost 1:1 with the underlying.'],
        ['Option', 'A contract that gives the right (not the obligation) to buy or sell at a fixed price. Costs a premium instead of the full contract value.'],
        ['CE (Call option)', 'Gains value as the underlying rises. Buying a CE profits from an up-move; selling one profits if the underlying stays below the strike.'],
        ['PE (Put option)', 'Gains value as the underlying falls. Buying a PE profits from a down-move; selling one profits if the underlying stays above the strike.'],
        ['Strike', 'The fixed price written into an option contract — e.g. a "23000 PE" pays out based on whether the underlying is above or below 23000 at expiry.'],
        ['Expiry', 'The date a contract stops trading and settles. NIFTY has weekly and monthly expiries; EdgeVest\'s strategies use whichever the trade card names.'],
        ['Lot / lot size', 'Contracts trade in fixed-size lots, not single units — "2 lots" of a contract with lot size 65 means 130 units of exposure.'],
        ['ITM / OTM', '"In the money" (the option already has intrinsic value) vs. "out of the money" (it doesn\'t, yet). EdgeVest\'s PE calendar spread specifically uses ITM puts — see that article.'],
        ['Leg', 'One contract within a multi-part trade. A trade with a FUT leg and a PE leg has two separate positions that together make up one strategy.'],
        ['Premium', 'The price paid (if buying) or received (if selling) for an option — separate from the strike, which never changes once the contract exists.'],
      ],
    },

    { type: 'heading', text: 'Words specific to how EdgeVest structures trades' },
    { type: 'list', items: [
      'Entry level / exit level — the index level a strategy triggers on. EdgeVest\'s NIFTY 500-Multiple strategy, for example, enters when the index crosses a round 500-point level and exits at a configured distance below it.',
      'Roll / auto-roll — replacing an expiring leg with the same structure on a later expiry, rather than just closing it. See the dedicated "What AUTO ROLL means" article.',
      'Adjustment — any change made to an already-open trade after entry: an exit, a roll, or a manual tweak. Every adjustment is logged, so a position\'s full history stays visible.',
      'Margin — the capital your broker blocks to hold a position, separate from the premium paid/received. See "Reading the Margin and P&L" for how EdgeVest shows this.',
    ] },

    { type: 'callout', text: 'This glossary explains terms — it isn\'t investment advice, and it doesn\'t tell you which trade to take. See the other Learn articles for how EdgeVest\'s specific strategies use these pieces.' },
  ],
}
