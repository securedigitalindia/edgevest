export default {
  slug: 'intrinsic-vs-time-value',
  title: 'Why options exist: intrinsic value vs. time value',
  category: 'fundamentals',
  summary: 'Every option\'s premium is made of two separate pieces that behave completely differently as expiry approaches.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'p', text: 'An option\'s premium — what you pay to buy it, or receive to sell it — is always made up of two separate pieces added together: intrinsic value and time value. Understanding the difference explains almost everything about how option prices actually move.' },

    { type: 'heading', text: 'Intrinsic value: what the option would be worth right now, if it expired this instant' },
    { type: 'p', text: 'A call option\'s intrinsic value is however much the underlying price is currently above the strike (zero if it isn\'t). A put option\'s intrinsic value is however much the underlying is currently below the strike (zero if it isn\'t). An option with intrinsic value is "in the money" (ITM); an option with none is "out of the money" (OTM) — it only has value because the market thinks it might gain some before expiry.' },

    { type: 'heading', text: 'Time value: what\'s left over' },
    { type: 'p', text: 'Subtract intrinsic value from the full premium and whatever remains is time value — the market\'s price for the *chance* the option becomes more valuable before it expires. An OTM option\'s entire premium is time value, since it has zero intrinsic value to start with.' },
    { type: 'p', text: 'Time value shrinks as expiry approaches — a phenomenon usually called decay. It doesn\'t shrink at a constant rate: it erodes slowly when there\'s a lot of time left and accelerates sharply in the final weeks and days before expiry. This is the single most important fact about time value, and it\'s the mechanical reason certain option structures (like calendar spreads) are built the way they are — see "What is a PE Calendar Spread?" for a concrete example.' },

    { type: 'heading', text: 'Why this matters when reading a price move' },
    { type: 'p', text: 'An option\'s price can fall even while the underlying moves in the "right" direction for it, if time decay eats away more value than the price move added — and it can rise on no price move at all, purely from rising uncertainty (the market pricing in a bigger possible swing ahead). Separating a premium into these two pieces is what makes an otherwise confusing price move explainable.' },

    { type: 'callout', text: 'This is general options mechanics, true of any options market — it\'s not specific to any one EdgeVest strategy, and it isn\'t advice on which option to buy or sell.' },
  ],
}
