import { useState } from 'react'
import { fmtRs } from '../../utils/format'
import { fmtDayLabel, fmtCompact, niceMax, dayOfMonth, posLabel, fmtPnlPlain } from './reportUtils'

// ─── Chart scaffolding (hand-rolled SVG, no charting dependency) ───────────
// Shared viewBox/padding so the margin and P&L charts line up visually.

const CW = 600, CH = 200
const PAD = { top: 14, right: 10, bottom: 22, left: 46 }
const PLOT_W = CW - PAD.left - PAD.right
const PLOT_H = CH - PAD.top - PAD.bottom

function xForDay(day, totalDays) {
  if (totalDays <= 1) return PAD.left + PLOT_W / 2
  return PAD.left + ((day - 1) / (totalDays - 1)) * PLOT_W
}

function ChartFrame({ yTicks, yFmt, xLabels, children, zeroY }) {
  return (
    <svg viewBox={`0 0 ${CW} ${CH}`} className="rep-chart-svg" preserveAspectRatio="xMidYMid meet">
      {/* gridlines + y-axis labels */}
      {yTicks.map(({ y, v }) => (
        <g key={y}>
          <line x1={PAD.left} y1={y} x2={CW - PAD.right} y2={y} className={v === 0 ? 'rep-chart-zeroline' : 'rep-chart-gridline'} />
          <text x={PAD.left - 6} y={y} className="rep-chart-ylabel" textAnchor="end" dominantBaseline="middle">{yFmt(v)}</text>
        </g>
      ))}
      {/* baseline axis */}
      <line x1={PAD.left} y1={zeroY} x2={CW - PAD.right} y2={zeroY} className="rep-chart-axis" />
      {/* x-axis labels — each entry controls its own `anchor` (defaults to
          'middle', for a label centered under a specific point) and
          optional `row` (0 or 1) to stagger a label onto a second line, for
          callers with several labels packed close enough on the x-axis
          that same-row text would collide (e.g. two exit-day bars a couple
          of days apart). */}
      {xLabels.map(({ x, label, row = 0, anchor = 'middle' }, i) => (
        <text key={i} x={x} y={CH - 4 - row * 9} className="rep-chart-xlabel" textAnchor={anchor}>{label}</text>
      ))}
      {children}
    </svg>
  )
}

function ChartEmpty({ label }) {
  return <div className="rep-chart-empty" style={{ aspectRatio: `${CW} / ${CH}` }}>{label}</div>
}

// ─── Margin-blocked-per-day: step/area chart ───────────────────────────────
// Not cumulative — each day's value is the net open margin that day, so this
// renders as an honest step function (entries push it up, exits pull it back
// down) rather than a smoothed line, per the PRD's explicit call-out.

export function MarginStepChart({ series, totalDays }) {
  const [hover, setHover] = useState(null)

  const hasData = series && series.length > 0 && series.some(s => s.margin > 0)
  if (!hasData) return <ChartEmpty label="No margin blocked yet this month." />

  const days = Math.max(totalDays, series.length)
  const max  = niceMax(Math.max(...series.map(s => s.margin), 0))
  const yScale = v => PAD.top + PLOT_H - (v / max) * PLOT_H
  const zeroY  = yScale(0)

  const pts = series.map(s => ({ x: xForDay(dayOfMonth(s.date), days), y: yScale(s.margin), date: s.date, margin: s.margin }))

  let line = `M ${pts[0].x} ${pts[0].y}`
  for (let i = 1; i < pts.length; i++) line += ` L ${pts[i].x} ${pts[i - 1].y} L ${pts[i].x} ${pts[i].y}`
  const area = `${line} L ${pts[pts.length - 1].x} ${zeroY} L ${pts[0].x} ${zeroY} Z`

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(f => ({ y: yScale(max * f), v: max * f }))
  const xLabels = [pts[0], pts[Math.floor((pts.length - 1) / 2)], pts[pts.length - 1]]
    .map((p, i, arr) => ({ x: p.x, label: fmtDayLabel(p.date), anchor: i === 0 ? 'start' : i === arr.length - 1 ? 'end' : 'middle' }))

  // Column width for hover targets — width per day, clamped to at least a
  // few px so a sparse (start-of-month) series is still easy to hover.
  const colW = pts.length > 1 ? PLOT_W / (pts.length - 1) : PLOT_W

  return (
    <div className="rep-chart-wrap">
      <ChartFrame yTicks={yTicks} yFmt={fmtCompact} xLabels={xLabels} zeroY={zeroY}>
        <path d={area} className="rep-margin-area" />
        <path d={line} className="rep-margin-line" />
        {hover != null && (
          <line x1={pts[hover].x} y1={PAD.top} x2={pts[hover].x} y2={zeroY} className="rep-chart-guide" />
        )}
        {pts.map((p, i) => (
          <rect key={i}
                x={p.x - colW / 2} y={PAD.top} width={colW} height={PLOT_H}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(h => (h === i ? null : h))} />
        ))}
        {hover != null && <circle cx={pts[hover].x} cy={pts[hover].y} r={3.5} className="rep-chart-dot" />}
      </ChartFrame>
      {hover != null && (
        <div className="rep-chart-tooltip" style={{ left: `${(pts[hover].x / CW) * 100}%`, top: `${(pts[hover].y / CH) * 100}%` }}>
          <div className="rep-tt-date">{fmtDayLabel(pts[hover].date)}</div>
          <div className="rep-tt-val">{fmtRs(pts[hover].margin)}</div>
        </div>
      )}
    </div>
  )
}

// ─── Realized P&L: net-booked-per-day bars ─────────────────────────────────
// Revised (was a cumulative running-sum line — see docs/prd/monthly-recommendation-report.md's
// "Decisions" section for the superseded original call). Changed because a
// smoothed/connected line implies continuous movement between exits that the
// data doesn't actually have — there's no intraday price series behind it,
// only a handful of discrete exit events. A day-based bar, matching the
// margin chart's own day-by-day x-axis, is honest about that: no bar means
// no exit that day, a bar's color is simply whether that day's net booked
// result was a gain or a loss (multiple same-day exits net into one bar).

export function PnlDailyBarChart({ events, totalDays }) {
  const [hover, setHover] = useState(null)

  if (!events || events.length === 0) return <ChartEmpty label="No positions exited this month." />

  // Multiple exits on the same day net together into one bar — same
  // granularity the margin chart already uses (one value per day).
  const byDay = new Map()
  events.forEach(e => {
    const d = dayOfMonth(e.exit_date)
    const cur = byDay.get(d) || { day: d, date: e.exit_date, net: 0, count: 0 }
    cur.net += e.realized_pnl
    cur.count += 1
    byDay.set(d, cur)
  })
  const bars = [...byDay.values()].sort((a, b) => a.day - b.day)

  const days = Math.max(totalDays, bars[bars.length - 1].day)
  const maxAbs = niceMax(Math.max(...bars.map(b => Math.abs(b.net)), 1))
  const yScale = v => PAD.top + PLOT_H / 2 - (v / maxAbs) * (PLOT_H / 2)
  const zeroY  = yScale(0)

  const pts  = bars.map(b => ({ ...b, x: xForDay(b.day, days), y: yScale(b.net) }))
  const barW = Math.max(6, Math.min(28, (PLOT_W / Math.max(days, 1)) * 0.6))

  const yTicks = [-1, -0.5, 0, 0.5, 1].map(f => ({ y: yScale(maxAbs * f), v: maxAbs * f }))
  // Every exit day gets its own x-axis label instead of just the month's
  // first/last day — a P&L bar is meaningless without knowing which day it
  // is, and there are rarely more than a handful of exit days in a month to
  // fit. Past ~10 bars, per-bar labels would start to collide, so fall back
  // to the margin chart's own sparser start/mid/end labeling in that case.
  // Per-bar labels always alternate rows (regardless of actual spacing) —
  // two exit days a couple of days apart (e.g. a roll's old/new legs
  // exiting close together) would otherwise overlap on a single line.
  const xLabels = pts.length <= 10
    ? pts.map((p, i) => ({ x: p.x, label: fmtDayLabel(p.date), row: i % 2 }))
    : [pts[0], pts[Math.floor((pts.length - 1) / 2)], pts[pts.length - 1]]
        .map((p, i, arr) => ({ x: p.x, label: fmtDayLabel(p.date), anchor: i === 0 ? 'start' : i === arr.length - 1 ? 'end' : 'middle' }))

  // Value labels sit right on the chart (not hover-only) so the reader
  // never has to guess a bar's magnitude from its height alone — small nets
  // especially can shrink to a barely-visible sliver next to a big one on
  // the same shared scale. Clamped inside the plot area so a near-max bar's
  // label can't clip past the top/bottom edge.
  const labelY = p => p.net >= 0
    ? Math.max(p.y - 6, PAD.top + 8)
    : Math.min(p.y + 14, CH - PAD.bottom - 4)

  return (
    <div className="rep-chart-wrap">
      <ChartFrame yTicks={yTicks} yFmt={fmtCompact} xLabels={xLabels} zeroY={zeroY}>
        {pts.map((p, i) => (
          <g key={i}
             opacity={hover === i || hover == null ? 1 : .55}
             onMouseEnter={() => setHover(i)}
             onMouseLeave={() => setHover(h => (h === i ? null : h))}>
            <rect x={p.x - barW / 2} y={Math.min(p.y, zeroY)} width={barW} height={Math.max(Math.abs(p.y - zeroY), 1)}
                  rx={2}
                  className={p.net >= 0 ? 'rep-pnl-bar-pos' : 'rep-pnl-bar-neg'} />
            <text x={p.x} y={labelY(p)} textAnchor="middle" className={`rep-chart-barlabel ${p.net >= 0 ? 'rep-chart-barlabel-pos' : 'rep-chart-barlabel-neg'}`}>
              {fmtCompact(p.net)}{p.count > 1 ? ` ×${p.count}` : ''}
            </text>
          </g>
        ))}
      </ChartFrame>
      {hover != null && (
        <div className="rep-chart-tooltip" style={{ left: `${(pts[hover].x / CW) * 100}%`, top: `${(pts[hover].y / CH) * 100}%` }}>
          <div className="rep-tt-date">{fmtDayLabel(pts[hover].date)}</div>
          <div className="rep-tt-val" style={{ color: pts[hover].net >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtPnlPlain(pts[hover].net)}</div>
          {pts[hover].count > 1 && <div className="rep-tt-sub">{pts[hover].count} positions exited</div>}
        </div>
      )}
    </div>
  )
}

// ─── Position lists — "which positions" behind each headline number ───────
// Charts show the shape; these lists show the actual trades so the numbers
// are never just an abstract line — every figure traces back to something
// concrete a reader can recognize (symbol + code) and click into if needed.

// `bookedOnly` is the Realized P&L tab's view of this same list — every
// position here already carries its own margin_at_entry AND (when it
// exited this month) its booked P&L, so there's no separate dataset/format
// needed for "what got booked": just this list, filtered down to the rows
// that actually have a booked amount, hiding the still-running ones (they
// have nothing to book yet). Kept as one shared component rather than a
// second list with its own layout, so margin and P&L views of "which
// positions" always read identically.
export function MarginPositionsList({ positions, month, atCurrentMonth, bookedOnly = false }) {
  if (!positions || positions.length === 0) {
    return <div className="empty">{bookedOnly ? 'No positions exited this month.' : 'No positions blocked margin this month.'}</div>
  }

  // A position's real exit_date can fall in a LATER month than the one being
  // viewed (carry-forward) — showing that future date here would read as
  // "already exited," making the margin look released during a month it was
  // actually still blocking. Only treat it as "exited" if the exit genuinely
  // happened within the month currently on screen.
  const annotated = positions
    .map(p => {
      const exitedThisMonth   = p.exit_date && p.exit_date.slice(0, 7) === month
      const stillOpenGlobally = !p.exit_date
      const carriedOrOpen     = stillOpenGlobally || (p.exit_date && !exitedThisMonth)
      return { ...p, exitedThisMonth, carriedOrOpen }
    })
    .filter(p => !bookedOnly || p.exitedThisMonth)

  if (bookedOnly && annotated.length === 0) {
    return <div className="empty">No positions exited this month.</div>
  }

  // Running first, closed-this-month after — within each group, keep the
  // backend's own margin-descending order (Array.prototype.sort is stable).
  // A no-op under bookedOnly (every remaining row is already !carriedOrOpen).
  const sorted = [...annotated].sort((a, b) => (a.carriedOrOpen === b.carriedOrOpen) ? 0 : a.carriedOrOpen ? -1 : 1)

  return (
    <div className="rep-pos-list">
      {sorted.map(p => {
        // The date-range text itself carries the full lifecycle now (no
        // separate badge chip needed) — the live current month never has a
        // real "month end" to compare against yet, so a still-running
        // position there just reads through to today; a past month's
        // running-at-the-time position instead shows the full progression
        // (entered → still counted through that month's end → what
        // happened since, if anything).
        let rangeText
        if (p.exitedThisMonth) {
          rangeText = `${fmtDayLabel(p.entry_date)} → ${fmtDayLabel(p.exit_date)}`
        } else if (atCurrentMonth) {
          rangeText = `${fmtDayLabel(p.entry_date)} → still open today`
        } else if (!p.exit_date) {
          rangeText = `${fmtDayLabel(p.entry_date)} → active till month end → still open today`
        } else {
          rangeText = `${fmtDayLabel(p.entry_date)} → active till month end → exited ${fmtDayLabel(p.exit_date)}`
        }

        return (
          <div key={p.trade_id} className={`rep-pos-row ${p.carriedOrOpen ? 'rep-pos-row-open' : ''}`}>
            <div className="rep-pos-main">
              <div className="rep-pos-label">{posLabel(p)}</div>
              <div className="rep-pos-sub">{rangeText}</div>
            </div>
            <div className="rep-pos-amt-col">
              <div className="rep-pos-amt">{fmtRs(p.margin_at_entry)}</div>
              {p.realized_pnl != null && (
                <div className="rep-pos-amt-sub" style={{ color: p.realized_pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {fmtPnlPlain(p.realized_pnl)} booked
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

