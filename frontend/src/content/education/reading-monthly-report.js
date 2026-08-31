export default {
  slug: 'reading-monthly-report',
  title: 'How to read the Monthly Report',
  category: 'numbers',
  summary: 'Why peak margin isn\'t a sum, why the margin chart moves up and down, and what "New" vs "Carried forward" means.',
  lastUpdated: '2026-09-01',
  body: [
    { type: 'heading', text: 'Peak margin isn\'t a total — it\'s a maximum' },
    { type: 'p', text: 'The Monthly Report walks through the month day by day and adds up the margin every position was blocking on that specific day — a position blocks margin from the day it opens through the day it exits, and releases it the moment it closes. "Peak Margin" is the single highest day in that walk, not the sum of every position\'s margin added together. It answers "what\'s the most capital this month ever needed at once," not "how much capital moved through the account in total."' },
    { type: 'p', text: 'This is also why the margin chart is a step shape rather than a straight climbing line — every entry pushes it up, every exit pulls it back down, on the actual calendar day each happened.' },

    { type: 'heading', text: 'Avg Margin is the ROI denominator' },
    { type: 'p', text: 'ROI is calculated against the month\'s average deployed capital, not the peak. Peak margin is a worst-case figure — the most that was ever needed at once — while average margin reflects what was typically actually at work, which is the fairer number to measure a return against.' },

    { type: 'heading', text: 'Booked vs Open' },
    { type: 'p', text: 'Every position that touched margin this month falls into exactly one of these two buckets: it either exited during the month ("Booked"), or it\'s still open as of the month\'s end ("Open"). For a past month, "Open" specifically means "still open when that month ended" — not "open today" — since a position can have been open at the end of July and since exited in August.' },

    { type: 'heading', text: 'New vs Carried forward' },
    { type: 'p', text: 'This is a different split from Booked/Open — it\'s about when a position actually started, not whether it has exited. "New" means it was opened within the month you\'re looking at. "Carried forward" means it was opened in an earlier month and is simply still touching margin this month. A position rolled forward at expiry (see "What AUTO ROLL means") still counts as new in the month it actually rolled — the roll creates a genuinely new trade record with its own margin, not a continuation of the old one\'s identity.' },

    { type: 'heading', text: 'Realised P&L books on the exit day, in full' },
    { type: 'p', text: 'A position\'s entire profit or loss is credited to the month it actually exited in — never split proportionally across however many months it was held. A trade opened in July and closed in September contributes nothing to July\'s or August\'s P&L and its full result to September\'s, however long the hold actually was. This keeps a month\'s numbers from silently changing later just because an old position eventually closes — but it also means an unusually large single-month P&L number can sometimes reflect a trade that was actually open for a while, not something that happened entirely within that one month.' },

    { type: 'callout', text: 'Every figure on this page is a look back at what already happened — none of it is a forecast for the month ahead.' },
  ],
}
