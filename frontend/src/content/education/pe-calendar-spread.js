export default {
  slug: 'pe-calendar-spread',
  title: 'What is a PE Calendar Spread?',
  category: 'strategies',
  summary: 'Why EdgeVest sometimes recommends selling one PE and buying another at the same strike, different expiry.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'p', text: 'A PE calendar spread is one of the structures EdgeVest recommends on NIFTY. It has two legs at the exact same strike price, but two different expiries:' },
    { type: 'list', items: [
      'SELL a put (PE) at the nearer expiry',
      'BUY a put (PE) at the same strike, further out expiry',
    ] },
    { type: 'p', text: 'Both legs use an ITM (in-the-money) strike — one that sits above the current price, so the put already has real, not just speculative, value. EdgeVest computes this strike as a fixed number of points above the current market price, then rounds it to the nearest tradable strike.' },

    { type: 'heading', text: 'Why the same strike, different expiry?' },
    { type: 'p', text: 'An option loses time value as it approaches expiry — this decay isn\'t linear, it accelerates in the final weeks. The near-expiry leg you\'re selling decays faster than the far-expiry leg you\'re holding, because it has less time left. The spread is structured to collect more from that faster decay on the short (sold) leg than it gives up on the long (bought) leg — the difference in how quickly each leg loses value is the reason the position exists at all.' },

    { type: 'heading', text: 'What you see on the trade card' },
    { type: 'p', text: 'The card names both legs directly — e.g. "SELL NIFTY 25 Aug 2026 23000 PE" and "BUY NIFTY 27 Oct 2026 23000 PE" — with the rationale line stating how far above the current price the strike sits. EdgeVest builds a few variants of this structure (both legs on quarterly expiries, both on monthly expiries, or a weekly leg paired against a monthly leg) depending on which specific setup the strategy has picked for that trade.' },

    { type: 'callout', text: 'This explains the structure EdgeVest is already recommending — it isn\'t a suggestion to build this trade independently, and the exact strike/expiry choice on any given day depends on live market levels at the time.' },
  ],
}
