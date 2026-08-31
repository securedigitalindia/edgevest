export default {
  slug: 'nifty-500-multiple',
  title: 'The NIFTY 500-Multiple Short strategy, explained',
  category: 'strategies',
  summary: 'What triggers an entry, why there are two legs, and what makes it exit — the logic behind this strategy\'s trade cards.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'p', text: 'This is one of EdgeVest\'s live, continuously-watched strategies on NIFTY. It doesn\'t run on a schedule — it watches every price tick and reacts the moment a specific condition is met.' },

    { type: 'heading', text: 'Entry: a round-500 level, crossed upward' },
    { type: 'p', text: 'NIFTY levels that are exact multiples of 500 (23000, 23500, 24000, …) act as the trigger. The moment NIFTY\'s price crosses UP through one of these levels, the strategy opens a new trade — never on a downward cross through the same level, only upward.' },
    { type: 'p', text: 'The entry is two legs, both sold, on the same expiry:' },
    { type: 'list', items: [
      'SELL the near-month NIFTY future',
      'SELL a NIFTY put (PE) at a strike comfortably below the current price — chosen so it stays at least a configured percentage away from the entry level, then rounded to the nearest 500-multiple strike',
    ] },
    { type: 'p', text: 'Both legs profit if NIFTY stays below where it entered — the short future gains as price falls (or at least doesn\'t rise further), and the sold put keeps its full premium as long as NIFTY stays above the put\'s strike.' },

    { type: 'heading', text: 'Exit: a configured point-drop from entry' },
    { type: 'p', text: 'Each trade carries its own exit level, set when it opens as a fixed number of points below the entry level. The moment NIFTY\'s price crosses down through that exit level, the strategy closes both legs — this is what shows up as an "exit" adjustment on the position.' },

    { type: 'heading', text: 'Why a position can outlive its original expiry' },
    { type: 'p', text: 'If NIFTY hasn\'t hit the exit level by the time the current expiry arrives, the strategy doesn\'t just let the contracts expire — on expiry day, it automatically rolls both legs forward to a new expiry, keeping the position open under a new trade record. See the "What AUTO ROLL means" article for exactly how that shows up on your position.' },

    { type: 'callout', text: 'This describes the mechanics of a strategy EdgeVest actively runs — it isn\'t personalized to your account, and it doesn\'t predict which level NIFTY will cross next.' },
  ],
}
