import { useMemo, useRef, useState } from 'react'
import { buildPanelSvg } from './dayChartSvg'

// Stacked panels (NIFTY on top, the strategy's debit / P&L / premiums below) on one shared time axis, with a hover crosshair.
// `panels` / `opts` follow dayChartSvg.js; `tipFor(i)` returns the tooltip lines for the hovered index.
export default function DayChart({ labels, panels, opts, tipFor, colors }) {
  const ref = useRef(null)
  const [hover, setHover] = useState(null)
  const built = useMemo(() => buildPanelSvg(labels, panels, { ...opts, colors }), [labels, panels, opts, colors])
  const { W, H, X, Lp, Rp } = built
  const n = labels.length

  const onMove = e => {
    const r = ref.current.getBoundingClientRect()
    const px = (e.clientX - r.left) / r.width * W
    const i = Math.max(0, Math.min(n - 1, Math.round((px - Lp) / (W - Lp - Rp) * (n - 1))))
    setHover({ i, left: X(i) / W * r.width, flip: X(i) / W > 0.6 })
  }

  return (
    <div className="dv-chart" ref={ref} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', maxWidth: '100%' }}
           fontFamily="IBM Plex Sans, system-ui, sans-serif" role="img" aria-label="Strategy chart">
        <g dangerouslySetInnerHTML={{ __html: built.svg }} />
        {hover && <line x1={X(hover.i)} x2={X(hover.i)} y1="4" y2={H - 30} stroke={colors.mut} opacity=".6" />}
      </svg>
      {hover && (
        <div className="dv-tip" style={hover.flip ? { right: `calc(100% - ${hover.left}px + 12px)` } : { left: hover.left + 12 }}>
          {tipFor(hover.i).map((l, k) => <div key={k} dangerouslySetInnerHTML={{ __html: l }} />)}
        </div>
      )}
    </div>
  )
}
