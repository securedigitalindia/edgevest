import { useEffect, useRef } from 'react'
import usePrices from '../../hooks/usePrices'
import './TickerStrip.css'

function fmtRs(v) {
  if (v == null) return '—'
  return '₹' + Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

export default function TickerStrip() {
  const { data: { spot, stale } = { spot: {}, stale: true } } = usePrices()
  const trackRef = useRef(null)

  useEffect(() => {
    const bar = trackRef.current
    if (!bar) return
    const entries = Object.entries(spot)
    if (!entries.length) return

    const onePass = entries.map(([sym, d]) => {
      const { ltp, change } = d
      const pos      = change != null && change >= 0
      const ltpColor = stale ? '#64748b' : (change == null ? '#e2e8f0' : (pos ? '#4ade80' : '#f87171'))
      const chgColor = change == null ? '#475569' : (pos ? '#4ade80' : '#f87171')
      const arrow    = change == null ? '' : (pos ? '▲' : '▼')
      const pct      = change != null && ltp ? ` ${pos?'+':''}${((change/ltp)*100).toFixed(2)}%` : ''
      const chgHtml  = change != null
        ? `<span class="tick-chg" style="color:${chgColor}">${arrow}${Math.abs(change).toLocaleString('en-IN',{maximumFractionDigits:0})}${pct}</span>`
        : ''
      return `<span class="tick-item"><span class="tick-sym">${sym}</span><span class="tick-ltp" style="color:${ltpColor}">${fmtRs(ltp)}</span>${chgHtml}</span>`
    }).join('')

    bar.innerHTML = onePass.repeat(4)
    bar.style.animationDuration = `${Math.max(18, entries.length * 7)}s`
  }, [spot, stale])

  return (
    <div className="ticker-strip">
      <div className="ticker-live-badge">
        <div className={`live-dot${stale ? ' stale' : ''}`} title="Green = live · Red = stale" />
        <span className="ticker-mkt-lbl">NSE</span>
      </div>
      <div className="ticker-clip">
        <div className="ticker-track" ref={trackRef} />
      </div>
    </div>
  )
}
