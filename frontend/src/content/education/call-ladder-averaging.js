export default {
  slug: 'call-ladder-averaging',
  title: 'Call ladder averaging: how it works and its risk shape',
  category: 'strategies',
  summary: 'A strategy pattern EdgeVest studies and backtests — not a live recommendation sent to your account today.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'callout', text: 'This is a strategy pattern EdgeVest researches and backtests — it is not currently a live, active recommendation sent to client accounts. It\'s included here so the mechanics and risk shape are understood before it ever might be.' },

    { type: 'heading', text: 'The base structure: a 1:1:1 call ladder' },
    { type: 'p', text: 'A "base" is a starting call ladder built from three legs at evenly spaced strikes, 1000 points apart:' },
    { type: 'list', items: [
      'BUY 1 lot at the base strike',
      'SELL 1 lot at base + 1000',
      'SELL 1 lot at base + 2000',
    ] },
    { type: 'p', text: 'That\'s two calls sold against one bought — a net short position above the highest strike, which is the source of the risk shape described below.' },

    { type: 'heading', text: 'Averaging: adding to the same ladder as it gets cheaper' },
    { type: 'p', text: 'Once a base ladder is on, its three exact strikes are watched going forward. If the cost to open that same three-leg structure again drops by a set percentage from what was last paid for it, another identical 1:1:1 set is added at the same three strikes. Each new addition resets the threshold off its own price — so the chain can keep extending as long as the ladder keeps getting cheaper to add to.' },

    { type: 'heading', text: 'The risk shape — read this carefully' },
    { type: 'p', text: 'Because each ladder sells two calls against only one bought call, the structure is net short one call above its highest strike. Below that strike, the position\'s downside is limited (bounded by what was paid to build it). Above it, losses are not capped in the same way a simple option purchase would be — the further the underlying rises past the top strike, the larger the loss grows, without an automatic ceiling. This unlimited-risk-above-the-top-strike characteristic is the single most important thing to understand about this pattern before ever evaluating it, live or backtested.' },
    { type: 'p', text: 'The backtested version of this pattern also holds every position open with no defined exit — every base and every average it accumulates stays on until the end of whatever window is being studied. A live version of this strategy, if EdgeVest ever activates one, would need its own exit/risk-management rules — those aren\'t part of what\'s described here.' },

    { type: 'callout', text: 'Described for understanding only. Nothing here is a live recommendation, and the unlimited-risk-above-the-top-strike shape means this pattern is materially different, risk-wise, from EdgeVest\'s active strategies described elsewhere in Learn.' },
  ],
}
