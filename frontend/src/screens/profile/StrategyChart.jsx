import { useRef, useState } from 'react'
import { fmtIstShort } from '../../utils/format'

// Direct port of the artifact's own hand-rolled SVG chart
// (backend/analysis/nifty_pe_ratio_diagonal_merged_windows_template.html's
// buildChart()) rather than a recharts approximation — the user asked
// twice for genuine visual/interaction parity with the artifact, and a
// generic charting library's own line/tooltip/grid rendering doesn't get
// there no matter how much it's restyled. Same technique: index-based x
// positioning (never real elapsed time — see StrategyChart's day-boundary
// comment below for why), a fixed 1000-unit viewBox that scales responsively
// via CSS width, and a pointermove-driven crosshair+tooltip computed from
// the SVG's own screen CTM.

const W = 1000, PAD_L = 54, PAD_R = 14, PAD_T = 26, PAD_B = 8

function niceTicks(min, max, count) {
  if (min === max) { min -= 1; max += 1 }
  const range = max - min
  const rawStep = range / count
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)))
  const norm = rawStep / mag
  let step
  if (norm < 1.5) step = 1 * mag; else if (norm < 3) step = 2 * mag; else if (norm < 7) step = 5 * mag; else step = 10 * mag
  const niceMin = Math.floor(min / step) * step
  const niceMax = Math.ceil(max / step) * step
  const ticks = []
  for (let v = niceMin; v <= niceMax + step * 1e-6; v += step) ticks.push(Math.round(v * 100) / 100)
  return ticks
}

const fmtNum = (n, dp = 1) => Number(n).toLocaleString('en-IN', { minimumFractionDigits: dp, maximumFractionDigits: dp })
const fmtDayLabel = ts => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short' }).format(new Date(ts))

/**
 * Generic index-positioned line chart. `points` must be pre-filtered/ordered
 * (one row per tick); each series' own value comes from `p[s.key]`.
 * `s.phase: true` splits the line at `p.post_exit` into a solid pre-exit
 * segment and a dashed/muted post-exit continuation (the "if held to
 * settlement" reference) — same convention as the artifact.
 */
export default function SvgChart({ points, series, yDomain, height, zeroLine, markers, exitTs, legend }) {
  const svgRef = useRef(null)
  const [hoverIdx, setHoverIdx] = useState(null)
  if (!points.length) return <div className="empty">No tick data for this window yet.</div>

  const n = points.length
  const [yMin, yMax] = yDomain
  const plotW = W - PAD_L - PAD_R, plotH = height - PAD_T - PAD_B
  const x = i => PAD_L + (n === 1 ? 0 : (i / (n - 1)) * plotW)
  const y = v => PAD_T + (1 - (v - yMin) / (yMax - yMin)) * plotH

  const ticks = niceTicks(yMin, yMax, 5).filter(t => t >= yMin && t <= yMax)

  const dayBoundaries = []
  for (let i = 1; i < n; i++) if (points[i].day !== points[i - 1].day) dayBoundaries.push(i)

  const exitIdx = exitTs ? points.findIndex(p => p.ts === exitTs) : -1

  function pathFor(vals, idxs) {
    let d = `M ${x(idxs[0])} ${y(vals[idxs[0]])}`
    for (const i of idxs.slice(1)) d += ` L ${x(i)} ${y(vals[i])}`
    return d
  }

  function handleMove(e) {
    const svg = svgRef.current
    if (!svg) return
    const pt = svg.createSVGPoint()
    pt.x = e.clientX; pt.y = e.clientY
    const loc = pt.matrixTransform(svg.getScreenCTM().inverse())
    const t = Math.max(0, Math.min(1, (loc.x - PAD_L) / plotW))
    setHoverIdx(Math.round(t * (n - 1)))
  }

  const hp = hoverIdx != null ? points[hoverIdx] : null
  const hx = hoverIdx != null ? x(hoverIdx) : 0
  const tooltipLeftFrac = hoverIdx != null ? hx / W : 0

  return (
    <div className="strat-chart-wrap">
      {legend && (
        <div className="strat-chart-legend">
          {legend.map(l => (
            <div key={l.label} className="strat-chart-legend-item">
              <span className={`strat-chart-legend-key ${l.dashed ? 'dashed' : ''}`} style={l.dashed ? undefined : { background: l.color }} />
              <span>{l.label}</span>
            </div>
          ))}
        </div>
      )}
      <div style={{ position: 'relative' }}>
        <svg ref={svgRef} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className="strat-chart-svg">
          {ticks.map(t => (
            <g key={t}>
              <line className="strat-chart-grid" x1={PAD_L} x2={W - PAD_R} y1={y(t)} y2={y(t)} />
              <text className="strat-chart-axis" x={PAD_L - 8} y={y(t) + 3} textAnchor="end">{t.toLocaleString('en-IN')}</text>
            </g>
          ))}
          {zeroLine && yMin < 0 && yMax > 0 && (
            <line className="strat-chart-zero" x1={PAD_L} x2={W - PAD_R} y1={y(0)} y2={y(0)} />
          )}

          {dayBoundaries.map(i => (
            <g key={`day-${i}`}>
              <line className="strat-chart-daybound" x1={x(i)} x2={x(i)} y1={PAD_T} y2={height - PAD_B} />
              <text className="strat-chart-daylabel" x={x(i) + 4} y={PAD_T - 10}>{fmtDayLabel(points[i].ts)}</text>
            </g>
          ))}

          {series.map(s => {
            const vals = points.map(p => p[s.key])
            const lastIdx = n - 1
            if (!s.phase) {
              return (
                <g key={s.key}>
                  <path className="strat-chart-line" d={pathFor(vals, points.map((_, i) => i))} stroke={s.color} />
                  <circle className="strat-chart-enddot" cx={x(lastIdx)} cy={y(vals[lastIdx])} r={4} fill={s.color} />
                </g>
              )
            }
            // Phase-split: solid pre-exit segments, dashed+muted post-exit segments,
            // bridged at the boundary so the dashed line starts exactly where solid ends.
            const segs = [[0]]
            const phaseOf = i => (points[i].post_exit ? 'post' : 'pre')
            for (let i = 1; i < n; i++) {
              if (phaseOf(i) === phaseOf(i - 1)) segs[segs.length - 1].push(i)
              else segs.push([i - 1, i])
            }
            return (
              <g key={s.key}>
                {segs.map((idxs, si) => {
                  const isPost = phaseOf(idxs[idxs.length - 1]) === 'post'
                  return <path key={si} className="strat-chart-line" d={pathFor(vals, idxs)} stroke={s.color}
                               strokeDasharray={isPost ? '5 4' : 'none'} opacity={isPost ? 0.5 : 1} />
                })}
                <circle className="strat-chart-enddot" cx={x(lastIdx)} cy={y(vals[lastIdx])} r={4} fill={s.color} />
              </g>
            )
          })}

          {markers && markers.map((m, i) => {
            const idx = points.findIndex(p => p.ts === m.ts)
            if (idx < 0) return null
            const xi = x(idx), yi = y(points[idx][m.key || 'fut'])
            return (
              <g key={i}>
                <line x1={xi} x2={xi} y1={PAD_T} y2={height - PAD_B} stroke={m.color} strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
                <circle className="strat-chart-trigger" cx={xi} cy={yi} r={5} fill={m.color} />
                <text className="strat-chart-triggerlabel" x={xi + 6} y={PAD_T + 10} fill={m.color}>{m.label}</text>
              </g>
            )
          })}

          {exitIdx >= 0 && (
            <g>
              <line x1={x(exitIdx)} x2={x(exitIdx)} y1={PAD_T} y2={height - PAD_B} stroke="var(--bad)" strokeWidth={1.5} opacity={0.75} />
              <text className="strat-chart-triggerlabel" x={x(exitIdx) + 6} y={height - PAD_B - 6} fill="var(--bad)">Exit</text>
            </g>
          )}

          <line className="strat-chart-crosshair" x1={hx} x2={hx} y1={PAD_T} y2={height - PAD_B} opacity={hoverIdx != null ? 1 : 0} />
          <rect x={PAD_L} y={0} width={plotW} height={height} fill="transparent" style={{ cursor: 'crosshair' }}
                onPointerMove={handleMove} onPointerLeave={() => setHoverIdx(null)} />
        </svg>
        {hp && (
          <div className="strat-chart-tooltip"
               style={{ left: `${Math.min(Math.max(tooltipLeftFrac * 100, 0), 100)}%`, transform: tooltipLeftFrac > 0.7 ? 'translateX(calc(-100% - 14px))' : 'translateX(14px)' }}>
            <div className="strat-chart-tooltip-date">{fmtIstShort(hp.ts)}</div>
            {series.map(s => (
              <div key={s.key} className="strat-chart-tooltip-row">
                <span className="strat-chart-tooltip-key" style={{ background: s.color }} />
                <span className="strat-chart-tooltip-label">{s.label}</span>
                <span className="strat-chart-tooltip-value">{fmtNum(hp[s.key], s.dp ?? 1)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
