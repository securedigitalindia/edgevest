import foGlossary from './fo-glossary'
import intrinsicVsTimeValue from './intrinsic-vs-time-value'
import understandingOptionsGreeks from './understanding-options-greeks'
import marginAndLeverage from './margin-and-leverage'
import peCalendarSpread from './pe-calendar-spread'
import nifty500Multiple from './nifty-500-multiple'
import autoRollExplained from './auto-roll-explained'
import callLadderAveraging from './call-ladder-averaging'
import readingMarginAndPnl from './reading-margin-and-pnl'
import readingMonthlyReport from './reading-monthly-report'

// Module structure inspired by Zerodha Varsity's IA (zerodha.com/varsity) —
// numbered, progressive modules rather than a flat list — without
// replicating its scale (Varsity runs ~17 modules, hundreds of chapters;
// this is 3 modules, 10 articles). See docs/prd/financial-education-content.md's
// 2026-09-01 revision for the full reasoning, including why Module 1 is the
// one deliberate exception to "platform-grounded content only."
export const MODULES = [
  {
    key: 'fundamentals',
    number: 1,
    title: 'F&O Fundamentals',
    description: 'General options/futures mechanics — the concepts EdgeVest\'s own strategies lean on without ever defining from scratch.',
    articles: [foGlossary, intrinsicVsTimeValue, understandingOptionsGreeks, marginAndLeverage],
  },
  {
    key: 'strategies',
    number: 2,
    title: 'EdgeVest Strategies Explained',
    description: 'What EdgeVest actually recommends, and why each structure is built the way it is.',
    articles: [peCalendarSpread, nifty500Multiple, autoRollExplained, callLadderAveraging],
  },
  {
    key: 'numbers',
    number: 3,
    title: 'Reading Your Numbers',
    description: 'How to interpret the margin, P&L, and report figures the app already shows you.',
    articles: [readingMarginAndPnl, readingMonthlyReport],
  },
]

export const ARTICLES = MODULES.flatMap(m => m.articles)

export function getArticleBySlug(slug) {
  return ARTICLES.find(a => a.slug === slug) || null
}
