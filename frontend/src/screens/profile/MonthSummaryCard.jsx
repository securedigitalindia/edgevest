import { useNavigate } from 'react-router-dom'
import { useMonthlyReport } from '../../hooks/useReports'
import { useRecs, useRecPrices } from '../../hooks/useTrades'
import { fmtRs } from '../../utils/format'
import { unrealizedPnl } from '../../utils/pnl'
import { monthLabel, shortMonthLabel, currentIstMonth, shiftMonth, roi, fmtPnlPlain } from './reportUtils'
import { BankIcon, TrendIcon } from '../../components/common/Icons'
import './MonthSummaryCard.css'

// ─── Monthly Report summary — booked (settled) vs running (live) split,
// same platform-wide numbers as /profile/reports
// (docs/prd/monthly-recommendation-report.md). Shared by Dashboard (home)
// and Trades (Recommended Positions) so both screens lead with the same
// at-a-glance monthly context before the reader drills into individual
// positions. Fully self-contained — own CSS file, own `msc-` class prefix —
// so it drops into either screen without pulling in that screen's unrelated
// styles or colliding with Reports.jsx's own, differently-purposed
// `rep-*` classes.
// ───────────────────────────────────────────────────────────────────────

// `compact` drops the "Monthly Report" header and the Avg/Peak Margin
// secondary row — just the split tile(s), for embedding inline on Trades
// rather than as its own standalone report summary.
//
// `status`/`onStatusChange` (`'open'` | `'exited'`) make this the actual
// status control, not just a display that mirrors one kept elsewhere:
// Trades.jsx no longer has its own Open/Exited dropdown — since this card's
// content (which tile, whether the month-nav even applies) and the position
// list below it both change on the very same toggle, the toggle itself now
// lives here, at the top of the card, and Trades.jsx's list filters off
// the lifted state this reports back. Dashboard never passes these (no
// concept of "the active filter" there) — omitting them renders both tiles,
// exactly as before.
//
// `month`/`onMonthChange` control the Booked tile's month picker (see
// monthNavEnabled below) — lifted to the caller for the same reason: Trades
// needs to filter its own position list by the same month the summary is
// showing, not just this card's own numbers. Only meaningful once `status`
// is being controlled at all.
export default function MonthSummaryCard({ compact = false, status, onStatusChange, month, onMonthChange } = {}) {
  const navigate = useNavigate()
  const nowMonth = currentIstMonth()
  const hasStatusToggle = compact && status != null
  const only = hasStatusToggle ? (status === 'open' ? 'running' : 'booked') : undefined
  // Booked-only is the one case that gets a month picker: Running is
  // inherently "right now" (live prices, live margin), so it never makes
  // sense to view it for a past month — but Booked is a closed, historical
  // number, and once it's the only tile on screen (the Exited side of the
  // toggle) the reader is explicitly asking "how did we do", which is
  // exactly the question a specific past month answers.
  const monthNavEnabled = hasStatusToggle && status === 'exited'
  const viewMonth = monthNavEnabled ? (month || nowMonth) : nowMonth
  const atCurrentMonth = viewMonth >= nowMonth
  // Only pass an explicit month once the reader has actually navigated away
  // from "now" — otherwise this keeps calling useMonthlyReport() with no
  // arg, sharing its TanStack Query cache (key ['monthly-report', undefined])
  // with every other current-month caller on the page (Dashboard's
  // FeaturedGrid, other MonthSummaryCard instances) instead of forking off
  // a redundant, differently-keyed fetch for the common case.
  const { data, isLoading } = useMonthlyReport(viewMonth === nowMonth ? undefined : viewMonth)

  // Running (unrealized) side — booked P&L comes straight from the backend
  // report (trades that actually exited this month), but "what am I sitting
  // on right now" only exists by combining every currently-open rec with
  // live prices, the same way Trades.jsx's RecItem does per-trade. useRecs()
  // shares its TanStack Query cache with wherever else on the page also
  // calls it (Trades' own RecsPanel, Dashboard's FeaturedGrid) — mounting
  // this card alongside them causes no extra fetch.
  const { data: recs = [] } = useRecs()
  const openRecs  = recs.filter(r => r.status === 'open')
  const instrKeys = [...new Set(
    openRecs.flatMap(r => [...(r.legs || []), ...(r.adjustments || []).flatMap(a => a.legs || [])])
            .map(l => l.instrument_key).filter(Boolean)
  )]
  const { data: prices = {} } = useRecPrices(instrKeys)
  const runningValues = openRecs.map(r => unrealizedPnl(r, prices)).filter(v => v != null)
  const runningPnl    = runningValues.reduce((a, b) => a + b, 0)
  const runningCount  = openRecs.length

  if (isLoading || !data || data.ok === false) return null

  const bookedPnl   = data.realized_pnl_total ?? 0
  const bookedCount = (data.pnl_events || []).length
  // ROI against average deployed capital, not the peak — peak is the
  // worst-case capital a month could demand, not what was typically at
  // work, so dividing by it understates the actual return in play.
  const bookedRoi = roi(bookedPnl, data.avg_margin_used)
  // Today's point on the margin series — the Running tile never gets a
  // month picker (see monthNavEnabled above), so this is always "now", the
  // same number the Reports page's own chart tooltip would show for today.
  const currentMarginUsed = data.margin_series?.length
    ? data.margin_series[data.margin_series.length - 1].margin
    : null
  // Running's own ROI — against the capital it's actually blocking right
  // now (not the month's average), since that's the number this tile is
  // otherwise reporting margin against. Still a mark-to-market ratio, not a
  // "final" one — it can move (including reversing) before it books.
  const runningRoi = runningCount > 0 ? roi(runningPnl, currentMarginUsed) : null

  const showBooked  = !only || only === 'booked'
  const showRunning = !only || only === 'running'

  // A tile click means "show me that status" — when this card already IS
  // the status control (Trades' own compact toggle), that's just a local
  // state flip, not a page change, so it must never go through navigate().
  // Doing so anyway was the bug: clicking a tile while already on Trades
  // pushed a fresh /trades?status=... history entry every time, so the
  // back button had to be pressed once per click before it would actually
  // leave the page. Only the Dashboard's non-toggle usage (only=undefined,
  // hasStatusToggle=false) is a genuine cross-page hop and still navigates.
  function goToStatus(targetStatus) {
    if (hasStatusToggle) onStatusChange?.(targetStatus)
    else navigate(`/trades?status=${targetStatus}`)
  }

  return (
    <>
      {!compact && (
        <div className="msc-sec-row">
          <div className="msc-section-label">Monthly Report</div>
          <button className="msc-sec-link" onClick={() => navigate('/profile/reports')}>View report →</button>
        </div>
      )}
      <div className={`card msc-hero-card msc-hero-card-clickable${compact ? ' msc-hero-card-compact' : ''}`} onClick={() => navigate('/profile/reports')}>
        {!compact && (
          <div className="msc-hero-top-row">
            <div className="msc-hero-label">{monthLabel(nowMonth)}</div>
            {/* positions_entered, not new_position_count: this pill's label
                is time-scoped ("this month"), so it wants every row entered
                in-range, rolls included — a roll is still a genuinely new
                row/margin, just linked to a prior position (see queries.py's
                get_monthly_report() docstring). new_position_count answers a
                different question (Reports.jsx's New/Rolled chips: of
                everything touching margin this month regardless of *when*
                it entered, how much is/isn't a rollover) — don't conflate
                the two here. */}
            <span className="msc-pill msc-pill-blue">{data.positions_entered ?? 0} new this month</span>
          </div>
        )}
        {hasStatusToggle && (
          // One bordered toolbar band for both controls — Open/Exited on
          // the left, the (Exited-only) month-nav on the right — rather
          // than two separately-centered floating rows stacked on top of
          // each other with no visual link between them.
          <div className="msc-toolbar" onClick={e => e.stopPropagation()}>
            <div className="msc-switch-inner" role="tablist" aria-label="Position status">
              {/* Same green/gray open-vs-exited dot used app-wide (Trades'
                  own RecItem, the old status dropdown) — index.css's global
                  .status-dot-*, not a new msc- one, since this is the one
                  existing convention for exactly this distinction. */}
              <button type="button" role="tab" aria-selected={status === 'open'} className={`msc-switch-btn ${status === 'open' ? 'msc-switch-btn-active' : ''}`} onClick={() => onStatusChange?.('open')}>
                <span className="status-dot status-dot-open"/> Open
              </button>
              <button type="button" role="tab" aria-selected={status === 'exited'} className={`msc-switch-btn ${status === 'exited' ? 'msc-switch-btn-active' : ''}`} onClick={() => onStatusChange?.('exited')}>
                <span className="status-dot status-dot-exited"/> Exited
              </button>
            </div>
            {monthNavEnabled && (
              <div className="msc-month-nav">
                <button type="button" className="msc-month-btn" onClick={() => onMonthChange?.(shiftMonth(viewMonth, -1))} aria-label="Previous month">‹</button>
                <span className="msc-month-label">{monthLabel(viewMonth)}{atCurrentMonth && <span className="msc-month-live">Live</span>}</span>
                <button type="button" className="msc-month-btn" onClick={() => onMonthChange?.(shiftMonth(viewMonth, 1))} disabled={atCurrentMonth} aria-label="Next month">›</button>
              </div>
            )}
          </div>
        )}

        <div className="msc-split">
          {/* Whole tile is the click target (not just a small count badge) —
              drills into Trades pre-filtered to that tile's status.
              stopPropagation'd against the card's own click-through to the
              report, so this always wins over it. ROI leads each tile (the
              figure that actually answers "was this worth it") — the label
              now says so explicitly ("Booked ROI"/"Running ROI") rather than
              leaving the reader to infer it from context, with a small
              trend-arrow icon chip (colored by that tile's own gain/loss,
              not by status) in place of the old bare status dot. The
              caption below follows the exact "{amount} realized on
              {capital}" sentence the Reports page's own ROI hero uses
              (Reports.jsx's `.rep-hero-sub`), amount bolded/colored, with a
              small bank icon on the capital figure to flag that margin —
              not just the P&L — is what the ROI is actually computed
              against. */}
          {showRunning && (
            <div className="msc-split-tile msc-split-running msc-split-tile-link"
                 onClick={e => { e.stopPropagation(); goToStatus('open') }}>
              <div className="msc-split-top">
                <span className="msc-split-lbl">
                  <span className="msc-split-icon msc-split-icon-running" style={{color: runningPnl >= 0 ? 'var(--green)' : 'var(--red)'}}><TrendIcon size={11} up={runningPnl >= 0}/></span>
                  Running ROI
                </span>
                <span className="msc-split-count">{runningCount} open</span>
              </div>
              <div className="msc-split-val" style={{color: runningCount === 0 ? 'var(--text)' : runningRoi.color}}>
                {runningCount === 0 ? '—' : runningRoi.text}
              </div>
              {runningCount > 0 && currentMarginUsed != null && (
                <div className="msc-split-foot">
                  <span className="msc-split-amt" style={{color: runningPnl >= 0 ? 'var(--green)' : 'var(--red)'}}>{fmtPnlPlain(runningPnl)}</span> unrealised on <BankIcon size={10}/> {fmtRs(currentMarginUsed)} margin blocked
                </div>
              )}
            </div>
          )}
          {showBooked && (
            <div className="msc-split-tile msc-split-booked msc-split-tile-link"
                 onClick={e => { e.stopPropagation(); goToStatus('exited') }}>
              <div className="msc-split-top">
                <span className="msc-split-lbl">
                  <span className="msc-split-icon msc-split-icon-booked" style={{color: bookedPnl >= 0 ? 'var(--green)' : 'var(--red)'}}><TrendIcon size={11} up={bookedPnl >= 0}/></span>
                  Booked ROI
                </span>
                <span className="msc-split-count">{bookedCount} exited</span>
              </div>
              <div className="msc-split-val" style={{color: bookedCount > 0 ? bookedRoi.color : 'var(--text)'}}>
                {bookedCount > 0 ? bookedRoi.text : '—'}
              </div>
              <div className="msc-split-foot">
                {bookedCount > 0
                  ? <><span className="msc-split-amt" style={{color: bookedPnl >= 0 ? 'var(--green)' : 'var(--red)'}}>{fmtPnlPlain(bookedPnl)}</span> realised on <BankIcon size={10}/> {fmtRs(data.avg_margin_used)} avg deployed</>
                  : atCurrentMonth ? 'Nothing exited yet this month' : `Nothing exited in ${shortMonthLabel(viewMonth)}`}
              </div>
            </div>
          )}
        </div>

        {!compact && (
          <div className="msc-hero-secondary">
            <div className="msc-hero-stat">
              <div className="msc-hero-stat-icon msc-hero-stat-icon-indigo"><BankIcon size={14}/></div>
              <div className="msc-hero-stat-lbl">Avg Margin</div>
              <div className="msc-hero-stat-val">{fmtRs(data.avg_margin_used)}</div>
            </div>
            <div className="msc-hero-stat">
              <div className="msc-hero-stat-icon msc-hero-stat-icon-amber"><TrendIcon size={14} up/></div>
              <div className="msc-hero-stat-lbl">Peak Margin</div>
              <div className="msc-hero-stat-val">{fmtRs(data.peak_margin_used)}</div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
