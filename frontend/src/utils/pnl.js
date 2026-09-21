// Shared per-recommendation P&L math. Realized P&L is the cash flow (SELL +,
// BUY -) over EVERY leg row — never entry-vs-exit pairing, which drops a leg
// closed mid-trade by an adjustment (no exit row exists for it). Mirrors
// net_realized_pnl() in backend/db/queries.py. Used by Trades.jsx's RecItem
// (per-trade) and Dashboard.jsx's monthly summary (aggregated across every
// open trade).

export function unrealizedPnl(rec, prices) {
  // 'draft' included so Trades.jsx's Draft Strategies card can show a live
  // running P&L the same way an open position does — the math is identical
  // (entry price vs current LTP), status only ever gated it because
  // 'exited'/legless rows don't have a meaningful "current" price to diff
  // against.
  if ((rec.status !== 'open' && rec.status !== 'draft') || !prices) return null
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

// Every leg row of a trade in chronological order: original entry, each
// adjustment's legs, then the final exit rows.
function allLegRows(rec) {
  return [...(rec.legs || []), ...(rec.adjustments || []).flatMap(a => a.legs || []), ...(rec.exit_legs || [])]
}

// Cash-flow P&L (SELL +, BUY -) over every leg row. A leg closed mid-trade by
// an adjustment has no exit_legs row, so pairing entries to exit rows drops it.
export function realizedPnl(rec) {
  if (rec.status !== 'exited' || !rec.exit_legs?.length) return null
  let total = 0
  for (const l of allLegRows(rec)) {
    if (l.price == null) return null
    const qty = (l.lots || 0) * (l.lot_size || 1)
    total += l.side === 'SELL' ? l.price * qty : -l.price * qty
  }
  return total
}

// Pairs each entry/adjustment leg with the price it was closed at, FIFO per
// instrument across all rows — the closing row may be an adjustment leg (a
// mid-trade roll) rather than an exit row. Returns [{ entry, exitLeg }] for
// `legs`, where exitLeg is { price, closedLots } (lot-weighted) or undefined, and `closes`
// is true when the leg is itself the closing row for earlier legs.
export function pairClosings(rec, legs) {
  const queues = {}
  const closed = new Map()
  const closers = new Set()
  for (const row of allLegRows(rec)) {
    const key = row.instrument_key || `id:${row.id}`
    const q = (queues[key] ||= [])
    let left = row.lots || 0
    while (left > 0 && q.length && q[0].row.side !== row.side) {
      const head = q[0]
      const take = Math.min(left, head.left)
      const c = closed.get(head.row) || { lots: 0, value: 0 }
      c.lots += take; c.value += take * row.price
      closed.set(head.row, c)
      head.left -= take; left -= take
      closers.add(row)
      if (head.left === 0) q.shift()
    }
    if (left > 0) q.push({ row, left })
  }
  return legs.map(l => {
    const c = closed.get(l)
    return { entry: l, exitLeg: c && c.lots ? { price: c.value / c.lots, closedLots: c.lots } : undefined, closes: closers.has(l) }
  })
}
