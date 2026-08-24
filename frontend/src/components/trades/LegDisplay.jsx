import { fmtRs, fmtPnl, fmtQty, fmtContract } from '../../utils/format'

// Shared leg-display primitives — used by Dashboard's RecItem (recommended
// positions) and Positions' TradeCard/HistoryCard (account positions), so
// both screens render the same kind of data (a position's legs) the same way.

export function OpenLeg({ leg: l, symbol, prices }) {
  const ltp    = prices && l.instrument_key ? prices[l.instrument_key] : null
  const qty    = (l.lots || 0) * (l.lot_size || 1)
  const legPnl = ltp != null && l.price != null
    ? (l.side === 'SELL' ? (l.price - ltp) * qty : (ltp - l.price) * qty)
    : null
  return (
    <div className="rec-leg-row">
      <span className={`leg-pill ${l.side === 'BUY' ? 'leg-pill-buy' : 'leg-pill-sell'}`}>{l.side}</span>
      <div className="rec-leg-name">
        <div className="rec-leg-sym">
          {l.symbol || symbol}
          {!!l.auto_adjust && <span title="auto-roll" style={{color:'#6366f1',fontSize:10,marginLeft:4}}>↻</span>}
        </div>
        {fmtContract(l) && <div className="rec-leg-contract">{fmtContract(l)}</div>}
      </div>
      <div style={{textAlign:'right',flexShrink:0}}>
        <div className="rec-leg-meta">{fmtQty(l.lots, l.lot_size, l.instrument_type)} · {fmtRs(l.price, 2)}{ltp != null ? ` → ${fmtRs(ltp, 2)}` : ''}</div>
        {legPnl != null && <div style={{fontSize:12,fontWeight:700,color:legPnl>=0?'var(--green)':'var(--red)'}}>{fmtPnl(legPnl)}</div>}
      </div>
    </div>
  )
}

export function ExitedLeg({ entry: e, exitLeg: x, symbol }) {
  const qty    = (e.lots || 0) * (e.lot_size || 1)
  const legPnl = e.price != null && x?.price != null
    ? (e.side === 'SELL' ? (e.price - x.price) * qty : (x.price - e.price) * qty)
    : null
  return (
    <div className="rec-leg-row">
      <span className={`leg-pill ${e.side==='BUY'?'leg-pill-buy':'leg-pill-sell'}`}>{e.side}</span>
      <div className="rec-leg-name">
        <div className="rec-leg-sym">{e.symbol || symbol}</div>
        {fmtContract(e) && <div className="rec-leg-contract">{fmtContract(e)}</div>}
      </div>
      <div style={{textAlign:'right',flexShrink:0}}>
        <div className="rec-leg-meta">{fmtQty(e.lots,e.lot_size,e.instrument_type)} · {fmtRs(e.price,2)} → {x ? fmtRs(x.price,2) : '—'}</div>
        {legPnl != null && <div style={{fontSize:12,fontWeight:700,color:legPnl>=0?'var(--green)':'var(--red)'}}>{fmtPnl(legPnl)}</div>}
      </div>
    </div>
  )
}

// `exitLegs`, when given, matches by instrument_key (not array position) —
// exit_legs is netted per instrument (original + adjustment on the same
// instrument share one exit row), so it can have fewer rows than `legs`.
// For callers that have already computed their own entry↔exit pairing
// (e.g. HistoryCard's positional pairing against account-trade exit legs,
// which aren't guaranteed to carry instrument_key), use `pairs` instead —
// an array of `{ entry, exitLeg }` rendered via ExitedLeg directly, skipping
// this component's own matching.
export default function LegGroup({ title, note, legs, symbol, type = 'entry', exitLegs, pairs, prices }) {
  return (
    <div className={`leg-group leg-group-${type}`}>
      {(title || note) && (
        <div className="leg-grp-hdr">
          {title}
          {note && <span className="leg-grp-note">{note}</span>}
        </div>
      )}
      {pairs
        ? pairs.map((p, i) => <ExitedLeg key={i} entry={p.entry} exitLeg={p.exitLeg} symbol={symbol} />)
        : legs.map((l, i) =>
            exitLegs
              ? <ExitedLeg key={i} entry={l} exitLeg={exitLegs.find(x => x.instrument_key && x.instrument_key === l.instrument_key)} symbol={symbol} />
              : <OpenLeg   key={i} leg={l} symbol={symbol} prices={prices} />
          )
      }
    </div>
  )
}
