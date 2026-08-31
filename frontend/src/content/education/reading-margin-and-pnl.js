export default {
  slug: 'reading-margin-and-pnl',
  title: 'Reading the Margin and P&L on your Recommended Positions',
  category: 'numbers',
  summary: 'What the margin figure actually is, and how the running P&L on an open position gets calculated.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'heading', text: 'Margin' },
    { type: 'p', text: 'Margin is the capital your broker blocks to hold a position — separate from any premium paid or received. EdgeVest shows the margin figure it captured at the moment the position was opened (or, for a rolled position, at the moment it rolled), computed via a live "what-if" margin check against the exact legs of that trade.' },
    { type: 'p', text: 'This is a snapshot, not a live number — it doesn\'t recompute every time you look at the app, and it doesn\'t chase small intraday moves in required margin. It\'s the figure that was accurate when the position actually opened, which is what the Monthly Report\'s margin-blocked figures are built from.' },

    { type: 'heading', text: 'P&L' },
    { type: 'p', text: 'The profit/loss shown on an open position is unrealised — a mark-to-market estimate using current live prices for every leg, not a locked-in number. It only becomes real ("booked" or "realised") once the position actually exits.' },
    { type: 'p', text: 'Where a trade has multiple legs (a calendar spread\'s two puts, or the fut+PE pair on the 500-Multiple strategy), each leg\'s current price is matched against its own original entry price — not the trade\'s legs matched up in whatever order they happen to be stored, but matched specifically by which contract they actually are, so a partial adjustment or a leg-level roll can never accidentally get compared against the wrong leg\'s entry price.' },

    { type: 'heading', text: 'Why margin and P&L are shown separately' },
    { type: 'p', text: 'They answer two different questions: margin is "how much capital is this position tying up right now," and P&L is "what is this position worth right now, relative to what it cost to open." A position can be using a lot of margin while barely moved in P&L, or a small amount of margin while showing a large P&L swing — the two numbers aren\'t meant to move together.' },

    { type: 'callout', text: 'Both figures describe a position\'s current state — neither is a prediction of what happens next, and unrealised P&L can move (including reversing) right up until the position actually exits.' },
  ],
}
