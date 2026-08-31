export default {
  slug: 'auto-roll-explained',
  title: 'What "AUTO ROLL" means on your position',
  category: 'strategies',
  summary: 'Why a position\'s ID changes at expiry without you doing anything, and why that\'s not a new trade.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'p', text: 'Some EdgeVest strategies (the NIFTY 500-Multiple strategy is one) hold a position across an expiry rather than closing it. When that happens, you\'ll see an "AUTO ROLL" adjustment on the position, and — the part that confuses people the first time — the trade\'s own identifier changes.' },

    { type: 'heading', text: 'What actually happens' },
    { type: 'p', text: 'On the expiry day of the contract a position is holding, once market hours reach the platform\'s configured roll time, EdgeVest:' },
    { type: 'list', items: [
      'Closes the expiring legs on the current trade, at the live price, exactly like a normal exit',
      'Immediately opens a new trade with the same structure on the next expiry, at the price then prevailing',
      'Links the new trade back to the old one, so its full history — including the position it continued from — stays visible',
    ] },
    { type: 'p', text: 'Economically, this is exiting one position and opening a fresh one seconds later — not the same contract magically continuing. That\'s also why it gets its own margin: a rolled position isn\'t assumed to need the same capital as the one it replaced, since the strike, expiry, and prevailing price have all changed.' },

    { type: 'heading', text: 'Why the trade "ID" changes' },
    { type: 'p', text: 'Because a roll genuinely closes one trade and opens another, the position you\'re watching gets a new trade record at that moment — you\'ll see its display code change (e.g. from an August-dated code to an October-dated one) even though, to you, it\'s the same ongoing strategy. The Positions and Trades screens show this lineage, so you can always trace a rolled position back to where it originally started.' },

    { type: 'heading', text: 'Why it matters for the numbers you see' },
    { type: 'p', text: 'A rolled trade\'s margin and P&L are tracked on its own record — the Monthly Report specifically separates "new" positions (opened fresh this month) from "carried forward" ones (still running from an earlier month) rather than treating every roll as brand-new activity. See "How to read the Monthly Report" for that split.' },

    { type: 'callout', text: 'A roll is a mechanical continuation of a strategy that\'s already running on your account — it isn\'t a new recommendation you\'re being asked to act on.' },
  ],
}
