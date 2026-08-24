// Shared formatting helpers (INR currency, quantities, IST timestamps).
// Extracted from Dashboard.jsx and the old settings drawer during the
// Positions/Profile page split — both used identical copies of these before.

export function fmtRs(v, dec = 0) {
  if (v == null) return '—'
  return '₹' + Number(v).toLocaleString('en-IN', { maximumFractionDigits: dec })
}

export function fmtPnl(v) {
  if (v == null) return '—'
  const n = Number(v)
  return (n >= 0 ? '+₹' : '−₹') + Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

export function fmtQty(lots, lotSize, type) {
  if (!lots) return '—'
  if (type === 'EQ') return `${lots} sh`
  const qty = lotSize ? lots * lotSize : lots
  return lotSize ? `${lots}L (${qty})` : `${lots}L`
}

export function fmtIstShort(ts) {
  if (!ts) return ''
  const d = new Date(ts.endsWith('Z') ? ts : ts + 'Z')
  return d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: true })
}

export function fmtContract(l) {
  return [l.strike ? Number(l.strike).toLocaleString('en-IN') : null, l.instrument_type, l.expiry_str]
    .filter(Boolean).join(' ')
}
