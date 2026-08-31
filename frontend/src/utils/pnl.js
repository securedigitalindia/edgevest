// Shared per-recommendation P&L math — instrument-key-matched, never the
// positional zip() used by GET /api/recommendations (docs/apis.md explains
// why: get_current_legs()/adjustments can leave fewer exit rows than the
// flattened entry+adjustment legs, so matching by array position silently
// mis-pairs or drops a leg). Used by Trades.jsx's RecItem (per-trade) and
// Dashboard.jsx's monthly summary (aggregated across every open trade).

export function unrealizedPnl(rec, prices) {
  if (rec.status !== 'open' || !prices) return null
  const legs = [...(rec.legs || []), ...(rec.adjustments || []).flatMap(a => a.legs || [])]
  let net = 0
  for (const l of legs) {
    const ltp = l.instrument_key && prices[l.instrument_key]
    if (!ltp) return null
    const qty = (l.lots || 0) * (l.lot_size || 1)
    net += l.side === 'SELL' ? (l.price - ltp) * qty : (ltp - l.price) * qty
  }
  return net
}

export function realizedPnl(rec) {
  if (rec.status !== 'exited' || !rec.exit_legs?.length) return null
  const entryLegs = [...(rec.legs || []), ...(rec.adjustments || []).flatMap(a => a.legs || [])]
  let total = 0, has = false
  entryLegs.forEach(e => {
    const x = rec.exit_legs.find(xl => xl.instrument_key && xl.instrument_key === e.instrument_key)
    if (e.price != null && x?.price != null) {
      const qty = (e.lots || 0) * (e.lot_size || 1)
      total += e.side === 'SELL' ? (e.price - x.price) * qty : (x.price - e.price) * qty
      has = true
    }
  })
  return has ? total : null
}
