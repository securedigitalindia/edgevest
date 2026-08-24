// Shared leg-builder helpers used by both CreateRecForm/AdjustForm (Dashboard.jsx)
// and NewTradeForm (Positions.jsx).

export function newLeg() {
  return { id: Date.now() + Math.random(), instrument: null, side: 'SELL', lots: '', price: '' }
}

export function collectLegs(legs, toast) {
  const out = []; let symbol = null
  for (const leg of legs) {
    if (!leg.instrument) { toast('Select an instrument for each leg', 'err'); return null }
    const lots  = parseInt(leg.lots)
    const price = parseFloat(leg.price)
    if (!lots || lots < 1)    { toast('Enter valid lots for each leg', 'err'); return null }
    if (!price || price <= 0) { toast('Enter valid price for each leg', 'err'); return null }
    symbol = leg.instrument.symbol
    const l = { side: leg.side, type: leg.instrument.instrument_type, lots, price }
    if (leg.instrument.instrument_key) l.instrument_key = leg.instrument.instrument_key
    if (leg.instrument.strike)         l.strike         = leg.instrument.strike
    if (leg.instrument.expiry_str)     l.expiry         = leg.instrument.expiry_str
    if (leg.instrument.lot_size)       l.lot_size       = leg.instrument.lot_size
    out.push(l)
  }
  return { symbol, legs: out }
}
