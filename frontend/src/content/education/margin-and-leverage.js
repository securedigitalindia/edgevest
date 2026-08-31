export default {
  slug: 'margin-and-leverage',
  title: 'Margin and leverage: how F&O capital works',
  category: 'fundamentals',
  summary: 'Why an F&O position lets you control much more exposure than the cash you actually put down.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'heading', text: 'Margin: a deposit, not the full cost' },
    { type: 'p', text: 'When you buy shares outright, you pay the full price. When you take a futures position (or sell an option), your broker instead blocks a deposit — margin — that\'s a fraction of the position\'s full value, sized to cover the likely worst-case move before the position could be closed out. The position gives you exposure to the full contract value while only your margin sits blocked.' },

    { type: 'heading', text: 'Leverage: the multiplier that creates' },
    { type: 'p', text: 'Because margin is a fraction of the full exposure, a relatively small amount of capital controls a much larger position — this ratio is leverage. It\'s exactly what makes F&O attractive (the same capital can capture a much bigger move than owning shares outright would) and exactly what makes it risky (losses scale with the full exposure, not just the margin put down — a moderate move against a highly leveraged position can wipe out the margin backing it far faster than the same move would on an unleveraged one).' },

    { type: 'heading', text: 'Margin isn\'t fixed — and it isn\'t yours to spend elsewhere' },
    { type: 'p', text: 'Required margin can change day to day as volatility and the position\'s own risk profile change — a broker may ask for more margin on a position that\'s become riskier, even with no change in direction. Margin blocked against one open position isn\'t available to open another until the first position closes and releases it — this is exactly why the Monthly Report tracks margin day-by-day rather than as a single running total: it\'s reused as positions open and close, not accumulated.' },

    { type: 'heading', text: 'Selling options carries a different margin shape than buying them' },
    { type: 'p', text: 'Buying an option has a known, capped cost — the premium paid, nothing more can be lost. Selling (writing) an option carries an obligation instead, and the margin required reflects that open-ended risk, which is why selling options generally blocks meaningfully more margin than buying the same option would cost in premium.' },

    { type: 'callout', text: 'General mechanics of how F&O margin works — see "Reading the Margin and P&L" for how EdgeVest specifically displays the margin figure on your own positions.' },
  ],
}
