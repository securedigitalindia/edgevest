import { useEffect, useMemo, useState } from 'react'
import { useDayList, useDay } from '../../hooks/useStrategies'
import usePrices from '../../hooks/usePrices'
import DayChart from './DayChart'
import './DayView.css'

// "Day view" for day-entry strategies — docs/prd/strategy-day-view.md. Pick a day: the entry is NIFTY's first touch of a
// 100-multiple after the open; one chart shows the position from before the entry to after it (or to live), and a table
// compares the neighbouring entry strikes. Research view only — not a trading signal. Prices are last-traded from the
// stored 5-minute option chain (no bid/ask), so "live" is as fresh as the poller's chain capture.

const COLORS = { ink: '#1e293b', mut: '#64748b', grid: '#e8edf3', card: '#ffffff', acc: '#2a78d6', up: '#16a34a', dn: '#dc2626', warn: '#b7791f', shade: 'rgba(42,120,214,.08)' }
const LEGCOL = [COLORS.dn, COLORS.up, COLORS.acc, COLORS.warn]

const f1  = v => v == null ? '–' : (Math.round(v * 10) / 10).toLocaleString('en-IN')
const sg  = v => v == null ? '–' : (v > 0 ? '+' : '') + f1(v)
const inr = v => v == null ? '–' : (v < 0 ? '−' : '') + '₹' + Math.abs(Math.round(v)).toLocaleString('en-IN')
const cls = v => v == null ? '' : v > 0 ? 'dv-up' : v < 0 ? 'dv-dn' : ''
const dshort = d => new Date(d + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
const legTxt = l => `${l.qty < 0 ? 'Sell' : 'Buy'} ${Math.abs(l.qty)} ${l.strike} ${l.opt}`
const rangeTxt = r => r ? `${f1(r[0])} – ${f1(r[1])}` : '–'

// Net debit = Σ qty × price (buys positive, sells negative); P&L = debit now − debit at entry. Generic over any number of legs.
function calcOne(rec, variant, off, legMeta) {
  const x = rec?.V?.[variant]?.[String(off)]
  if (!x || x.skip) return { skip: x ? x.skip : 'no data', pending: !!x?.pending }
  const n = rec.spot.length, legs = x.legs
  const deb = rec.spot.map((_, i) => { let s = 0; for (const g of legs) { if (g.px[i] == null) return null; s += g.qty * g.px[i] } return s })
  const debit0 = legs.reduce((a, g) => a + g.qty * g.px0, 0)
  const pnl = deb.map(q => q == null ? null : q - debit0)
  const pS = rec.day0 ? rec.d.indexOf(rec.d[rec.day0 - 1]) : 0
  const nE = rec.day1 < n ? rec.d.lastIndexOf(rec.d[rec.day1]) + 1 : n
  const rng = (a, b) => { const q = deb.slice(a, b).filter(z => z != null); return q.length ? [Math.min(...q), Math.max(...q)] : null }
  const lastOf = (a, b) => { for (let i = b - 1; i >= a; i--) if (deb[i] != null) return deb[i]; return null }
  const hasNext = rec.day1 < n
  return {
    x, legs, deb, pnl, debit0, n, hasNext,
    prev: rec.day0 ? rng(pS, rec.day0) : null, today: rng(rec.touch.i, rec.day1), next: hasNext ? rng(rec.day1, nE) : null,
    prevClose: rec.day0 ? lastOf(pS, rec.day0) : null, close: lastOf(rec.day0, rec.day1), nextClose: hasNext ? lastOf(rec.day1, nE) : null,
    thin: legs.some((g, k) => g.oi != null && g.oi < (legMeta?.[k]?.thin_oi ?? 0)), stale: legs.some(g => g.st),
  }
}

export default function DayView({ strategy }) {
  const sid = strategy.id
  const { data: list, isLoading: loadingList } = useDayList(sid)
  const days = useMemo(() => (list?.days || []), [list])
  const variants = list?.variants || strategy.variants || []

  const [day, setDay] = useState(null)
  const [variant, setVariant] = useState(null)
  const [off, setOff] = useState(0)
  const [before, setBefore] = useState(1)
  const [after, setAfter] = useState('live')
  const [metric, setMetric] = useState('D')
  const [lot, setLot] = useState(null)
  const [sets, setSets] = useState(1)

  useEffect(() => { if (list && !day) setDay(list.days[list.days.length - 1]?.date || null) }, [list, day])
  useEffect(() => { if (list && !variant) setVariant(list.variants[0]) }, [list, variant])
  useEffect(() => { if (list && lot == null) setLot(list.lot) }, [list, lot])

  const entry = days.find(d => d.date === day)
  const isLive = !!entry?.live
  const { data: rec, isLoading, error } = useDay(sid, day, variant, isLive)

  // Live NIFTY from the shared 5 s price poll (no extra request) — drawn as a "now" point on the NIFTY panel for the live day.
  const { data: spotData } = usePrices()
  const liveSpot = spotData?.spot?.NIFTY50?.ltp ?? null

  if (loadingList) return <div className="empty">Loading…</div>
  if (!days.length) return <div className="empty">No option-chain data captured yet.</div>

  const offs = list.offs || []
  const mult = (lot || 1) * (sets || 1)

  return (
    <div className="dv">
      <div className="dv-controls">
        <label>Day
          <select value={day || ''} onChange={e => setDay(e.target.value)}>
            {[...days].reverse().map(d => <option key={d.date} value={d.date}>{dshort(d.date)}{d.level ? ` · ${d.level} at ${d.time}` : ' · waiting for touch'}{d.live ? ' · LIVE' : ''}</option>)}
          </select>
        </label>
        <label>Variant
          <div className="dv-seg">{variants.map(v => <button key={v} type="button" className={v === variant ? 'on' : ''} onClick={() => setVariant(v)}>{v}</button>)}</div>
        </label>
        <label>Entry strike
          <select value={off} onChange={e => setOff(+e.target.value)}>
            {[...offs].reverse().map(o => <option key={o} value={o}>{o === 0 ? `Auto: first touch${entry?.level ? ' ' + entry.level : ''}` : `${o > 0 ? '+' : '−'}${Math.abs(o) * list.step}${entry?.level ? ` → ${entry.level + o * list.step}` : ''}`}</option>)}
          </select>
        </label>
        <label>Days before
          <select value={before} onChange={e => setBefore(+e.target.value)}>{[1, 2, 3, 5, 7].map(k => <option key={k} value={k}>− {k} day{k > 1 ? 's' : ''}</option>)}</select>
        </label>
        <label>Days after
          <select value={after} onChange={e => setAfter(e.target.value)}>
            {isLive && <option value="live">To live</option>}
            {[1, 2, 3, 5, 7, 14, 21, 30].map(k => <option key={k} value={k}>+ {k} day{k > 1 ? 's' : ''}</option>)}
          </select>
        </label>
        <label>Chart shows
          <div className="dv-seg">
            {[['D', 'Debit'], ['P', 'P&L'], ['R', 'Premiums']].map(([k, t]) => <button key={k} type="button" className={metric === k ? 'on' : ''} onClick={() => setMetric(k)}>{t}</button>)}
          </div>
        </label>
        <label>Lot size<input type="number" min="1" value={lot || ''} onChange={e => setLot(Math.max(1, +e.target.value || 1))} /></label>
        <label>Sets<input type="number" min="1" value={sets} onChange={e => setSets(Math.max(1, +e.target.value || 1))} /></label>
      </div>

      {isLoading && <div className="empty">Computing this day from the option chain… (first load can take a few seconds)</div>}
      {error && <div className="empty">Could not load this day.</div>}
      {rec && !rec.ok && <div className="empty">{rec.error || 'No data for this day.'}</div>}
      {rec?.ok && <DayBody rec={rec} meta={list} variant={variant} off={off} before={before} after={after} metric={metric}
                           mult={mult} lot={lot} onPickOff={setOff} liveSpot={isLive ? liveSpot : null} />}
    </div>
  )
}

function DayBody({ rec, meta, variant, off, before, after, metric, mult, lot, onPickOff, liveSpot }) {
  const T = rec.touch

  // Not touched yet (live day before the first 100-multiple touch) — show where NIFTY is relative to the nearest levels.
  if (!T) {
    const w = rec.watch || {}
    const spot = liveSpot ?? w.spot
    return (
      <div className="dv-card">
        <h3>Waiting for the first touch</h3>
        <p className="dv-sub">No {meta.step}-multiple has been touched yet today. NIFTY {f1(spot)}{liveSpot ? ' (live)' : ` (as of ${rec.as_of})`}: nearest levels are {w.down} ({f1(spot - w.down)} below) and {w.up} ({f1(w.up - spot)} above). The entry is taken at the first 5-minute snapshot within {meta.near} points of a level, or that jumped through one.</p>
      </div>
    )
  }

  const L = T.level
  const R = metric === 'R', M = metric === 'D'
  const c = calcOne(rec, variant, off, meta.legs)

  if (c.skip) {
    return <div className="dv-card"><p className="dv-sub">{variant} entry at {L + off * meta.step} {c.pending ? 'has no price yet' : 'has no price'} on {dshort(rec.date)}: {c.skip}.
      {c.pending ? ' It may still get its first trade within the hour.' : ' The stored option chain has no usable price there, so nothing can be computed. Try another strike, the other variant, or another day.'}</p></div>
  }

  const { legs, n } = c
  const j0 = c.x.j
  const pn = c.nextClose != null ? c.nextClose - c.debit0 : null
  const flag = (c.thin ? '⚠ thin open interest ' : '') + (c.stale ? '⚠ stale price' : '')

  // window: calendar days before / after the entry day
  const dayMs = s => Date.parse(s + 'T00:00:00Z'), e0 = dayMs(rec.date)
  const a = Math.max(0, rec.d.findIndex(x => dayMs(x) >= e0 - before * 864e5))
  let b = rec.d.length
  if (after !== 'live') while (b > 0 && dayMs(rec.d[b - 1]) > e0 + (+after) * 864e5) b--
  const nd = new Set(rec.d.slice(a, b)).size
  const win = nd <= 3 ? 1 : 2
  const sl = x => x.slice(a, b), jr = j0 - a
  const showNow = rec.live && liveSpot != null && b === n
  let labels = sl(rec.t).map((tm, i) => win === 1 ? tm : dshort(rec.d[a + i]) + ' ' + tm)
  const pad = arr => showNow ? [...arr, null] : arr
  if (showNow) labels = [...labels, 'now']

  const legSeries = legs.map((g, k) => ({ name: `${legTxt(g)} premium${Math.abs(g.qty) > 1 ? ' ×' + Math.abs(g.qty) : ''}`, y: pad(sl(g.px.map(p => p == null ? null : Math.abs(g.qty) * p))), color: LEGCOL[k % 4], w: 2.2, split: jr }))
  const series = R
    ? [...legSeries, { name: 'Net debit', y: pad(sl(c.deb)), color: COLORS.ink, w: 3, split: jr }]
    : [{ name: M ? 'Net debit' : 'P&L', y: pad(sl(M ? c.deb : c.pnl)), color: COLORS.ink, w: 3, split: jr }]
  const hl = (M || R) ? [{ y: c.debit0, label: 'entry debit ' + f1(c.debit0), color: COLORS.acc }] : []
  const vl = []
  for (let i = a; i < b; i++) if ((nd <= 10 || i === rec.day0) && (i === a || rec.d[i] !== rec.d[i - 1])) vl.push({ i: i - a, label: i === rec.day0 ? 'entry day' : dshort(rec.d[i]), color: i === rec.day0 ? COLORS.acc : COLORS.mut, strong: i === rec.day0 })
  const spotY = pad(sl(rec.spot)); if (showNow) spotY[spotY.length - 1] = liveSpot

  const panels = [
    { h: 150, title: 'NIFTY', fmt: q => Math.round(q).toLocaleString('en-IN'), series: [{ name: 'NIFTY', y: spotY, color: COLORS.acc, w: 2 }],
      hlines: [{ y: L, label: 'touch ' + L, color: COLORS.mut }], marks: [{ i: jr, v: rec.spot[j0], label: 'entry', color: COLORS.acc }] },
    { h: 270, title: R ? 'Leg premiums (pts)' : M ? 'Net debit (pts)' : 'P&L (pts)', zero: !M && !R, series, hlines: hl,
      marks: [{ i: jr, v: (M || R ? c.deb : c.pnl)[j0], label: 'entry', color: COLORS.ink }] },
  ]
  const opts = { shade: [0, jr], xt: win === 1 ? 12 : 9, vlines: vl, vlabels: nd <= 10 }
  const tipFor = i => {
    if (showNow && i === labels.length - 1) return [`<b>now</b>`, `NIFTY ${f1(liveSpot)} (live)`]
    const k = a + i
    return [`<b>${win === 1 ? dshort(rec.d[k]) + ' ' : ''}${rec.t[k]}</b>`, `NIFTY ${f1(rec.spot[k])}`,
      legs.map(g => `${g.role} ${g.strike}: ${f1(g.px[k])}`).join(' · '), `debit ${f1(c.deb[k])} · P&amp;L ${sg(c.pnl[k])}`]
  }

  const tiles = [['First touch', `${L}`, `${T.time} IST · NIFTY ${f1(T.spot)} · ${T.kind === 'cross' ? 'jumped through' : `within ${meta.near} pts`}`]]
  legs.forEach(g => tiles.push([`${g.qty < 0 ? 'Sell' : 'Buy'} ${Math.abs(g.qty)}`, `${g.strike} ${g.opt}`, `${g.exp} · ${f1(g.px0)}${Math.abs(g.qty) > 1 ? ' each = ' + f1(Math.abs(g.qty) * g.px0) : ''} · OI ${(g.oi || 0).toLocaleString('en-IN')}`]))
  const k0 = tiles.length
  tiles.push(['Entry debit (− = credit)', `${f1(c.debit0)} pts`, `${inr(c.debit0 * mult)}${c.x.lag ? ` · priced ${c.x.lag} min after the touch (first trade)` : ''}${flag ? ' · ' + flag : ''}`],
    ['Day before', rangeTxt(c.prev), `debit range · close ${f1(c.prevClose)}`],
    ['Entry day (after entry)', rangeTxt(c.today), `debit range · close ${f1(c.close)}`],
    ['Day after', c.hasNext ? rangeTxt(c.next) : 'no data yet', c.hasNext ? `debit range · close ${f1(c.nextClose)}` : ''],
    ['P&L at day-after close', c.hasNext ? sg(pn) : '–', c.hasNext ? inr(pn * mult) : ''])

  return (
    <>
      <div className="dv-card">
        <h3>{dshort(rec.date)} · {variant} · {legs.map(legTxt).join(' · ')}{rec.live && <span className="dv-live">LIVE · data to {rec.as_of}</span>}</h3>
        <p className="dv-sub">{R ? "Each leg's premium (× its quantity) and the net debit between them." : M ? 'Net debit in points = Σ quantity × premium (buys positive, sells negative). Going up means the position got more expensive to hold.' : 'P&L in points since entry = change in net debit.'} Dashed and shaded is before the entry (what it would have shown). Hover for premiums and NIFTY.{showNow ? ' The last point is live NIFTY.' : ''}</p>
        <DayChart labels={labels} panels={panels} opts={opts} tipFor={tipFor} colors={COLORS} />
        <div className="dv-legend">
          {series.map(s => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}
          <span><i style={{ background: COLORS.acc }} />NIFTY</span>
        </div>
      </div>

      <div className="dv-tiles">
        {tiles.map(([k, v, s], i) => (
          <div className="dv-tile" key={k + i}>
            <div className="dv-k">{k}</div>
            <div className={`dv-v ${i === tiles.length - 1 ? cls(pn) : ''} ${i === k0 && flag ? 'dv-warn' : ''}`} style={i > k0 && i < tiles.length - 1 ? { fontSize: 15 } : undefined}>{v}</div>
            <div className="dv-s">{s}</div>
          </div>
        ))}
      </div>

      <div className="dv-card">
        <h3>Premiums and debit by entry strike</h3>
        <p className="dv-sub">Entry premiums at {T.time} ({meta.offs.length} entry strikes), then the net debit at each close. Click a row to select it.</p>
        <div className="dv-table-wrap">
          <table className="dv-table">
            <thead><tr><th>Entry strike</th><th>Legs</th>{legs.map(g => <th key={g.role}>{g.role} px</th>)}<th>Entry debit</th><th>Day-before close</th><th>Entry-day close</th><th>Day-after close</th><th>P&amp;L day-after</th><th /></tr></thead>
            <tbody>
              {[...meta.offs].reverse().map(o => {
                const k = calcOne(rec, variant, o, meta.legs)
                const label = o === 0 ? `Auto: first touch ${L}` : `${o > 0 ? '+' : '−'}${Math.abs(o) * meta.step} → ${L + o * meta.step}`
                if (k.skip) return <tr key={o} className="dv-row" onClick={() => onPickOff(o)}><td>{label}</td><td colSpan={legs.length + 7} className="dv-nodata">no price: {k.skip}</td></tr>
                const p = k.nextClose != null ? k.nextClose - k.debit0 : null
                return (
                  <tr key={o} className={`dv-row ${o === off ? 'sel' : ''}`} onClick={() => onPickOff(o)}>
                    <td>{label}</td><td>{k.legs.map(g => g.strike).join(' / ')}</td>
                    {k.legs.map((g, ix) => <td key={ix}>{f1(g.px0)}</td>)}
                    <td>{f1(k.debit0)}</td><td>{f1(k.prevClose)}</td><td>{f1(k.close)}</td><td>{f1(k.nextClose)}</td>
                    <td className={cls(p)}>{sg(p)}</td><td className="dv-warn">{(k.thin ? '⚠ thin ' : '') + (k.stale ? '⚠ stale' : '')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="dv-card dv-notes">
        <b>Notes</b>
        <ul>
          <li><b>Strategy:</b> {meta.description}</li>
          <li><b>Entry rule:</b> first 5-minute snapshot where NIFTY is within {meta.near} points of a multiple of {meta.step}, or jumped through one. The open counts.</li>
          <li><b>Expiries:</b> {legs.map(g => `${g.role.toLowerCase()} ${g.exp}`).join(', ')}.</li>
          <li><b>Prices</b> are last-traded from the stored 5-minute chain, not bid/ask — &quot;live&quot; is as fresh as the poller&apos;s chain capture (about 5 minutes), with the NIFTY point updating every 5 s. ⚠ = thin open interest or a price that did not move for 30 minutes. No brokerage, slippage, margin or exit rule. Lot {lot} is not verified. Days far from the entry are stored at coarser time steps (entry day 5 min, ±2 days 15 min, rest hourly).</li>
          <li>Research view, not a trading signal.</li>
        </ul>
      </div>
    </>
  )
}
