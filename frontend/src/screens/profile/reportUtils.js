// Shared pure helpers for the Monthly Report screen (Reports.jsx) and its
// chart/position-list pieces (ReportCharts.jsx). All month math happens on
// plain 'YYYY-MM' strings computed against the IST wall-clock date, never
// against the browser's local timezone — mirrors the backend's own "IST
// calendar month" framing (docs/prd/monthly-recommendation-report.md).

const IST_DISPLAY_MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

// Recommendation objects (GET /api/recommendations) only ever carry a
// pre-formatted `entry_ist`/`exit_ist` string — "23 Aug 2026  19:50 IST",
// server.py's `_ist_str()` — never the raw UTC timestamp. Deliberately not
// `new Date(str)`: a bare "IST" zone abbreviation isn't reliably parsed
// across browsers. Since this codebase controls both ends of the format,
// parse the fixed "DD Mon YYYY" prefix directly instead.
export function istMonthFromDisplay(str) {
  if (!str) return null
  const m = /^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})/.exec(str)
  if (!m) return null
  const monthIdx = IST_DISPLAY_MONTHS.indexOf(m[2])
  if (monthIdx === -1) return null
  return `${m[3]}-${String(monthIdx + 1).padStart(2, '0')}`
}

export function currentIstMonth() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit' }).formatToParts(new Date())
  const y = parts.find(p => p.type === 'year').value
  const m = parts.find(p => p.type === 'month').value
  return `${y}-${m}`
}

export function shiftMonth(month, delta) {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(Date.UTC(y, m - 1 + delta, 1))
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
}

export function monthLabel(month) {
  const [y, m] = month.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-IN', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

// Short form for inline badges ("Jul") — monthLabel()'s full "July 2026" is
// too long once it's sitting next to a date range and an amount.
export function shortMonthLabel(month) {
  const [y, m] = month.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-IN', { month: 'short', timeZone: 'UTC' })
}

export function daysInMonth(month) {
  const [y, m] = month.split('-').map(Number)
  return new Date(Date.UTC(y, m, 0)).getUTCDate()
}

export function dayOfMonth(dateStr) {
  return parseInt(dateStr.slice(8, 10), 10)
}

// 'YYYY-MM-DD' → "6 Aug", read as IST midnight (no implicit UTC-shift).
export function fmtDayLabel(dateStr) {
  return new Date(`${dateStr}T00:00:00+05:30`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

// Compact axis labels (₹8.1L) — headline stats still use the full fmtRs().
export function fmtCompact(v) {
  return '₹' + new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(v)
}

// ROI = realized P&L booked this month ÷ the peak capital actually deployed
// to earn it — not ÷ every rupee that ever touched a position, since margin
// is reused as positions close (see the margin card's own caption). No
// meaningful ratio exists with zero capital deployed, so that's "—", not 0%.
// No "+" on a gain — the green color already says "up"; a negative pct's
// own "-" from toFixed() still comes through untouched.
export function roi(pnl, peakMargin) {
  if (!peakMargin) return { text: '—', color: 'var(--muted)' }
  const pct = (pnl / peakMargin) * 100
  return { text: `${pct.toFixed(1)}%`, color: pnl >= 0 ? 'var(--green)' : 'var(--red)' }
}

// Same as utils/format.js's fmtPnl() but without the "+" on a gain — used
// throughout the Reports screens where color already carries the sign and a
// leading "+" reads as redundant noise on every single figure on the page.
// Kept local (not a change to the shared fmtPnl) since Trades/Positions/
// LegDisplay all rely on fmtPnl's "+" today and weren't asked to change.
export function fmtPnlPlain(v) {
  if (v == null) return '—'
  const n = Number(v)
  return (n < 0 ? '−₹' : '₹') + Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

export function niceMax(v) {
  if (v <= 0) return 1
  const mag  = Math.pow(10, Math.floor(Math.log10(v)))
  const norm = v / mag
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10
  return nice * mag
}

// Days between two 'YYYY-MM-DD' strings, inclusive of both ends — read as IST
// midnight so this can't drift a day depending on the browser's own timezone.
export function daysHeld(entryDate, exitDate) {
  const ms = new Date(`${exitDate}T00:00:00+05:30`) - new Date(`${entryDate}T00:00:00+05:30`)
  return Math.round(ms / 86400000) + 1
}

export function posLabel(p) {
  return p.display_code ? `${p.symbol} · ${p.display_code}` : p.symbol
}
