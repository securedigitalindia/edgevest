import { useMemo, useState } from 'react'
import { useMonthlyReport } from '../../hooks/useReports'
import PageHeader from '../../components/common/PageHeader'
import { fmtRs } from '../../utils/format'
import { MarginStepChart, PnlDailyBarChart, MarginPositionsList, PnlPositionsList } from './ReportCharts'
import { currentIstMonth, shiftMonth, monthLabel, shortMonthLabel, daysInMonth, roi, fmtPnlPlain } from './reportUtils'
import { BankIcon, TrendIcon } from '../../components/common/Icons'
import './Reports.css'

export default function Reports() {
  // Visible to both clients and admins — the report itself is platform-wide
  // (recommended_trades aggregate), not account-specific, so there's nothing
  // client-sensitive to gate here beyond the app shell's own login gate.
  const nowMonth = currentIstMonth()
  const [month, setMonth] = useState(nowMonth)
  const [chartView, setChartView] = useState('margin') // 'margin' | 'pnl' — one chart card, one metric at a time
  const { data, isLoading } = useMonthlyReport(month)
  const atCurrentMonth = month >= nowMonth
  const totalDays = useTotalDaysShown(month, atCurrentMonth, data)
  // ROI is against average deployed capital, not the peak — peak is the
  // worst-case capital a month could demand, not what was typically at work;
  // dividing by it understates the actual return on the capital in play.
  const roiStat = roi(data?.realized_pnl_total, data?.avg_margin_used)

  const marginPositions   = data?.margin_positions || []
  const totalPositions    = marginPositions.length
  const bookedCount       = (data?.pnl_events || []).length
  const openAtMonthEnd    = totalPositions - bookedCount
  const stillOpenToday    = marginPositions.filter(p => !p.exit_date).length
  const showStillOpenNote = !atCurrentMonth && stillOpenToday !== openAtMonthEnd

  return (
    <div className="profile-page">
      <PageHeader title="Monthly Report" fallback="/profile" />

      <div className="rep-month-nav">
        <button className="rep-month-btn" onClick={() => setMonth(m => shiftMonth(m, -1))} aria-label="Previous month">‹</button>
        <div className="rep-month-label">
          {monthLabel(month)}
          {atCurrentMonth && <span className="rep-live-chip">Live</span>}
        </div>
        <button className="rep-month-btn" onClick={() => setMonth(m => shiftMonth(m, 1))} disabled={atCurrentMonth} aria-label="Next month">›</button>
      </div>

      {isLoading && <div className="empty">Loading…</div>}
      {!isLoading && data && data.ok === false && <div className="empty">{data.error || 'Failed to load report.'}</div>}

      {!isLoading && data && data.ok !== false && (
        <>
          <div className="card rep-hero-card">
            <div className="rep-hero-label">ROI this month</div>
            <div className="rep-hero-value" style={{ color: roiStat.color }}>{roiStat.text}</div>
            <p className="rep-hero-sub">
              {fmtPnlPlain(data.realized_pnl_total ?? 0)} realized on {fmtRs(data.avg_margin_used)} average capital deployed
            </p>

            {/* Position counts — Booked vs Open is the one split that
                actually partitions "Total": every position touching this
                month's margin either exited during it or is still open as of
                its end, nothing else. "New this month" (positions_entered) is
                a different, overlapping axis — it can include carry-forward
                rolls and never sums with Booked/Open — so it rides along as
                a plain qualifier on the total line instead of sitting in the
                split as if it were a third slice of the same pie. Booked/Open
                colored to match the exited/open convention used everywhere
                else (Trades page, Dashboard's own Booked/Running split card).

                Historical framing matters here: for a PAST month, "open" must
                mean "still open when that month ended", not "open today" —
                a position can be open at July's end and have since exited in
                August. Using !exit_date (open right now) would undercount a
                past month's open figure and silently break the invariant
                Total = Booked + Open. margin_positions only ever contains
                rows that are either (a) exited within THIS month (already
                counted in bookedCount) or (b) still open at/after this
                month's end — so Total − Booked is exactly "open as of this
                month's end", no extra filter needed. For the current month,
                "month end" and "today" are the same instant, so this still
                reduces to the live count Dashboard shows. */}
            <div className="rep-count-row">
              <div className="rep-count-total">
                <span className="rep-count-total-val">{totalPositions}</span> position{totalPositions === 1 ? '' : 's'} touched margin this month
                {(data.positions_entered ?? 0) > 0 && <span className="rep-count-new"> · {data.positions_entered} new</span>}
              </div>
              <div className="rep-count-split">
                <div className="rep-count-tile rep-count-tile-booked">
                  <div className="rep-count-tile-top"><span className="rep-dot rep-dot-booked" />{atCurrentMonth ? 'Booked' : `Booked in ${shortMonthLabel(month)}`}</div>
                  <div className="rep-count-tile-val">{bookedCount}</div>
                </div>
                <div className="rep-count-tile rep-count-tile-open">
                  <div className="rep-count-tile-top"><span className={`rep-dot rep-dot-open${atCurrentMonth ? ' is-live' : ''}`} />{atCurrentMonth ? 'Open now' : `Open · end of ${shortMonthLabel(month)}`}</div>
                  <div className="rep-count-tile-val">{openAtMonthEnd}</div>
                  {showStillOpenNote && <div className="rep-count-tile-note">{stillOpenToday} still open today</div>}
                </div>
              </div>
            </div>

            <div className="rep-hero-secondary">
              <div className="rep-hero-stat">
                <div className="rep-hero-stat-icon rep-hero-stat-icon-indigo"><BankIcon size={14}/></div>
                <div className="rep-hero-stat-lbl">Avg Margin</div>
                <div className="rep-hero-stat-val">{fmtRs(data.avg_margin_used)}</div>
              </div>
              <div className="rep-hero-stat">
                <div className="rep-hero-stat-icon rep-hero-stat-icon-amber"><TrendIcon size={14} up/></div>
                <div className="rep-hero-stat-lbl">Peak Margin</div>
                <div className="rep-hero-stat-val">{fmtRs(data.peak_margin_used)}</div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header rep-card-header rep-switch-header">
              <h2>{chartView === 'margin' ? 'Margin Blocked Per Day' : 'Realized P&L'}</h2>
              <div className="rep-switch" role="tablist" aria-label="Chart metric">
                <button type="button" role="tab" aria-selected={chartView === 'margin'} className={`rep-switch-btn ${chartView === 'margin' ? 'rep-switch-btn-active' : ''}`} onClick={() => setChartView('margin')}>Margin</button>
                <button type="button" role="tab" aria-selected={chartView === 'pnl'} className={`rep-switch-btn ${chartView === 'pnl' ? 'rep-switch-btn-active' : ''}`} onClick={() => setChartView('pnl')}>P&amp;L</button>
              </div>
              {chartView === 'margin' ? (
                <p className="rep-card-caption">
                  Net margin across every recommended position still open that day — not cumulative, since margin
                  frees up the moment a position exits. <strong>Peak</strong> is the minimum capital needed to run
                  every position concurrently, at 1-lot sizing.
                </p>
              ) : (
                <p className="rep-card-caption">
                  Net P&amp;L booked on each day a recommended position exited this month — not cumulative, since there&rsquo;s
                  no intraday price series to justify a smooth line between exits. A position&rsquo;s full profit/loss always
                  books on its <strong>exit</strong> day; a long-held trade&rsquo;s number here can look large relative to how
                  briefly it shows up, so check its hold duration in the list below before comparing months.
                </p>
              )}
            </div>
            <div className="card-body">
              {chartView === 'margin'
                ? <MarginStepChart series={data.margin_series || []} totalDays={totalDays} />
                : <PnlDailyBarChart events={data.pnl_events || []} totalDays={totalDays} monthStart={month} />}
            </div>
            <div className="rep-pos-section-title">Positions behind this number</div>
            <div className="card-body rep-pos-body">
              {chartView === 'margin'
                ? <MarginPositionsList positions={data.margin_positions || []} month={month} atCurrentMonth={atCurrentMonth} />
                : <PnlPositionsList events={data.pnl_events || []} month={month} />}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// Days shown on the x-axis: full calendar month once it's in the past,
// capped at "today" for the in-progress current month — matches the
// backend's own effective_end_utc framing so the chart's x-domain never
// implies data that couldn't exist yet.
function useTotalDaysShown(month, atCurrentMonth, data) {
  return useMemo(() => {
    const full = daysInMonth(month)
    if (!atCurrentMonth) return full
    const todayIst = parseInt(
      new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', day: '2-digit' }).format(new Date()), 10
    )
    return Math.min(full, Math.max(todayIst, data?.margin_series?.length || 1))
  }, [month, atCurrentMonth, data])
}
