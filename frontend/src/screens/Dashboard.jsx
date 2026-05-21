import { useState, useEffect, useRef } from 'react'
import { useRecs, useRecPrices, useCreateRec, useDeleteRec, useExitRec, useAdjustRec, useCreateAccountTrade,
         useTrades, useTradeHistory, useExitTrade, useApplyAdjTrade, useDeleteTrade,
         useAccounts } from '../hooks/useTrades'
import useAuthStore from '../store/authStore'
import { searchInstruments } from '../api/trades'
import { useToast } from '../components/common/Toast'
import './Dashboard.css'

const ADJ_COLORS = ['#fffbeb', '#eff6ff', '#f0fdf4', '#fdf4ff']

function fmtRs(v, dec = 0) {
  if (v == null) return '—'
  return '₹' + Number(v).toLocaleString('en-IN', { maximumFractionDigits: dec })
}
function fmtPnl(v) {
  if (v == null) return '—'
  const n = Number(v)
  return (n >= 0 ? '+₹' : '−₹') + Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}
function fmtQty(lots, lotSize, type) {
  if (!lots) return '—'
  if (type === 'EQ') return `${lots} sh`
  const qty = lotSize ? lots * lotSize : lots
  return lotSize ? `${lots}L (${qty})` : `${lots}L`
}

function collectLegs(legs, toast) {
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

// ─── Instrument search typeahead ─────────────────────────────────────────────

function InstrumentSearch({ value, onSelect }) {
  const [query, setQuery]     = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen]       = useState(false)
  const [focused, setFocused] = useState(-1)
  const timerRef = useRef(null)
  const wrapRef  = useRef(null)

  useEffect(() => {
    function onClickOut(e) { if (!wrapRef.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('click', onClickOut)
    return () => document.removeEventListener('click', onClickOut)
  }, [])

  function handleChange(e) {
    const q = e.target.value
    setQuery(q); setFocused(-1)
    clearTimeout(timerRef.current)
    if (q.length < 2) { setOpen(false); setResults([]); return }
    timerRef.current = setTimeout(async () => {
      const res = await searchInstruments(q)
      setResults(res); setOpen(res.length > 0)
    }, 300)
  }

  function handleKey(e) {
    if (!open) return
    if      (e.key === 'ArrowDown') { e.preventDefault(); setFocused(f => Math.min(f + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp')   { e.preventDefault(); setFocused(f => Math.max(f - 1, 0)) }
    else if (e.key === 'Enter' && focused >= 0) { e.preventDefault(); pick(results[focused]) }
    else if (e.key === 'Escape')    setOpen(false)
  }

  function pick(item) { setOpen(false); setQuery(''); setResults([]); onSelect(item) }

  if (value) return (
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'5px 10px',background:'#eff6ff',border:'1px solid #bfdbfe',borderRadius:6,marginBottom:6}}>
      <span style={{fontSize:12,color:'#1d4ed8',fontWeight:500,flex:1}}>{value.label}</span>
      <button style={{background:'none',border:'none',color:'#93c5fd',cursor:'pointer',fontSize:14}} onClick={() => onSelect(null)}>✕</button>
    </div>
  )

  return (
    <div ref={wrapRef} style={{position:'relative',marginBottom:6}}>
      <input placeholder="Search: nifty 25000 ce  /  banknifty fut"
             value={query} onChange={handleChange} onKeyDown={handleKey} autoComplete="off" />
      {open && (
        <div style={{position:'absolute',top:'100%',left:0,right:0,zIndex:200,background:'#fff',
                     border:'1px solid var(--border)',borderTop:'none',borderRadius:'0 0 8px 8px',
                     maxHeight:180,overflowY:'auto',boxShadow:'0 6px 16px rgba(0,0,0,.1)'}}>
          {results.map((r, i) => (
            <div key={i} style={{padding:'8px 12px',cursor:'pointer',fontSize:13,
                                 borderBottom:'1px solid #f1f5f9',
                                 background:i===focused?'#eff6ff':'#fff'}}
                 onMouseEnter={() => setFocused(i)} onClick={() => pick(r)}>{r.label}</div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Leg builder ─────────────────────────────────────────────────────────────

function newLeg() { return { id: Date.now() + Math.random(), instrument: null, side: 'SELL', lots: '', price: '' } }

function LegBuilder({ legs, onChange }) {
  function add()            { onChange([...legs, newLeg()]) }
  function remove(id)       { onChange(legs.filter(l => l.id !== id)) }
  function update(id, f, v) { onChange(legs.map(l => l.id === id ? { ...l, [f]: v } : l)) }

  return (
    <div>
      <div style={{display:'flex',flexDirection:'column',gap:10,marginBottom:10}}>
        {legs.map((leg, i) => (
          <div key={leg.id} style={{border:'1px solid var(--border)',borderRadius:8,padding:'10px 10px 8px',background:'#fafafa',position:'relative'}}>
            <div style={{fontSize:11,fontWeight:700,color:'var(--muted)',textTransform:'uppercase',letterSpacing:.5,marginBottom:6}}>Leg {i + 1}</div>
            {legs.length > 1 && (
              <button style={{position:'absolute',top:8,right:8,background:'none',border:'none',color:'#cbd5e1',fontSize:16,padding:0,cursor:'pointer'}}
                      onClick={() => remove(leg.id)}>✕</button>
            )}
            <InstrumentSearch value={leg.instrument} onSelect={ins => update(leg.id, 'instrument', ins)} />
            {leg.instrument && (
              <div style={{display:'grid',gridTemplateColumns:'80px 70px 1fr',gap:8}}>
                <div>
                  <label>Side</label>
                  <select value={leg.side} onChange={e => update(leg.id, 'side', e.target.value)}>
                    <option>BUY</option><option>SELL</option>
                  </select>
                </div>
                <div>
                  <label>{leg.instrument.instrument_type === 'EQ' ? 'Qty' : 'Lots'}</label>
                  <input type="number" min="1" placeholder="1" value={leg.lots}
                         onChange={e => update(leg.id, 'lots', e.target.value)} />
                </div>
                <div>
                  <label>Price</label>
                  <input type="number" step="0.05" placeholder="0.00" value={leg.price}
                         onChange={e => update(leg.id, 'price', e.target.value)} />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <button style={{width:'100%',padding:7,border:'1.5px dashed #cbd5e1',borderRadius:6,background:'none',color:'var(--muted)',cursor:'pointer',fontSize:13}}
              onClick={add}>+ Add Leg</button>
    </div>
  )
}

// ─── Create recommendation form (admin) ──────────────────────────────────────

function CreateRecForm() {
  const [legs, setLegs] = useState([newLeg()])
  const [note, setNote] = useState('')
  const create = useCreateRec()
  const toast  = useToast()

  async function submit() {
    const data = collectLegs(legs, toast)
    if (!data) return
    const res = await create.mutateAsync({ ...data, note })
    if (res.ok) {
      toast(`Recommendation created (id=${res.trade_id}) ✓`, 'ok')
      setLegs([newLeg()]); setNote('')
    } else {
      toast(res.error || 'Create failed', 'err')
    }
  }

  return (
    <div className="card">
      <div className="card-header"><h2>New Recommendation</h2></div>
      <div className="card-body">
        <LegBuilder legs={legs} onChange={setLegs} />
        <div className="form-row" style={{marginTop:12}}>
          <label>Note (optional)</label>
          <input placeholder="e.g. Bull put spread" value={note} onChange={e => setNote(e.target.value)} />
        </div>
        <button className="btn btn-primary" style={{width:'100%',justifyContent:'center',marginTop:4}}
                onClick={submit} disabled={create.isPending}>
          Create &amp; Send Alert
        </button>
      </div>
    </div>
  )
}

// ─── Rec leg display (open legs and exit-paired legs) ─────────────────────────

function LegGroupSection({ label, legs, rec, exitLegs, exitOffset, bg, isExited }) {
  const renderOpenLeg = (l, i) => (
    <div key={i} className="rec-leg-row">
      <span className={l.side === 'BUY' ? 'side-buy' : 'side-sell'} style={{fontWeight:700,minWidth:38}}>{l.side}</span>
      <div className="rec-leg-name">
        <div className="rec-leg-sym">
          {l.symbol || rec.symbol}
          {!!l.auto_adjust && <span title="auto-roll" style={{color:'#6366f1',fontSize:10,marginLeft:3}}>↻</span>}
        </div>
        <div className="rec-leg-contract">
          {l.strike ? Number(l.strike).toLocaleString('en-IN') + ' ' : ''}{l.instrument_type}{l.expiry_str ? ' · ' + l.expiry_str : ''}
        </div>
      </div>
      <span className="rec-leg-meta">{fmtQty(l.lots, l.lot_size, l.instrument_type)} @{fmtRs(l.price, 2)}</span>
    </div>
  )

  const renderExitPair = (entry, exitLeg, i) => {
    const sc  = entry.side === 'BUY' ? 'side-buy' : 'side-sell'
    const xsc = exitLeg?.side === 'BUY' ? 'side-buy' : 'side-sell'
    const ep  = fmtRs(entry.price, 2)
    const xp  = exitLeg?.price != null ? fmtRs(exitLeg.price, 2) : '—'
    const qty = (entry.lots || 0) * (entry.lot_size || 1)
    const legPnl = (entry.price != null && exitLeg?.price != null)
      ? (entry.side === 'SELL' ? (entry.price - exitLeg.price) * qty : (exitLeg.price - entry.price) * qty)
      : null
    const sym      = entry.symbol || rec.symbol
    const contract = `${entry.strike ? Number(entry.strike).toLocaleString('en-IN') + ' ' : ''}${entry.instrument_type}${entry.expiry_str ? ' · ' + entry.expiry_str : ''}`
    return (
      <div key={i} className="exit-block" style={{background:bg}}>
        <div style={{fontSize:13,fontWeight:700,color:'#1e293b'}}>{sym}</div>
        <div style={{fontSize:11,color:'var(--muted)',marginBottom:3}}>{contract}</div>
        <div style={{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
          <span className={sc} style={{fontWeight:700}}>{entry.side}</span>
          {exitLeg && <><span style={{color:'var(--muted)'}}>→</span><span className={xsc} style={{fontWeight:700}}>{exitLeg.side}</span></>}
          <span style={{fontSize:12,color:'var(--muted)'}}>{ep}{exitLeg ? ` → ${xp}` : ''}</span>
          <span style={{fontSize:12,color:'var(--muted)'}}>{fmtQty(entry.lots, entry.lot_size, entry.instrument_type)}</span>
          {legPnl != null && <span style={{fontSize:11,fontWeight:600,color:legPnl>=0?'var(--green)':'var(--red)'}}>{fmtPnl(legPnl)}</span>}
        </div>
      </div>
    )
  }

  return (
    <div style={{background:bg,borderRadius:6,padding:'4px 8px 2px',marginBottom:4}}>
      <div className="leg-grp-hdr">{label}</div>
      {isExited
        ? legs.map((l, i) => renderExitPair(l, exitLegs?.[exitOffset + i], i))
        : legs.map((l, i) => renderOpenLeg(l, i))
      }
    </div>
  )
}

function RecLegs({ rec }) {
  const isExited = rec.status === 'exited'
  return (
    <div className="rec-legs">
      <LegGroupSection label="Entry" legs={rec.legs} rec={rec}
        exitLegs={rec.exit_legs} exitOffset={0} bg="#f8fafc" isExited={isExited} />
      {(rec.adjustments || []).map((a, ai) => {
        const bg     = ADJ_COLORS[ai % ADJ_COLORS.length]
        const offset = isExited ? rec.legs.length + (rec.adjustments || []).slice(0, ai).reduce((s, a2) => s + (a2.legs?.length || 0), 0) : 0
        return (
          <LegGroupSection key={a.id || ai}
            label={`Adjustment ${ai + 1}${a.note ? ' · ' + a.note : ''}`}
            legs={a.legs || []} rec={rec}
            exitLegs={rec.exit_legs} exitOffset={offset} bg={bg} isExited={isExited} />
        )
      })}
    </div>
  )
}

// ─── Push to account form (client) ───────────────────────────────────────────

function PushForm({ rec, prices, onClose }) {
  const { data: accounts = [] } = useAccounts()
  const [acctId, setAcctId]     = useState('')
  const [legData, setLegData]   = useState(rec.legs.map(l => {
    const ltp = prices && l.instrument_key ? prices[l.instrument_key] : null
    return { lots: String(l.lots), price: String(ltp ?? l.price ?? '') }
  }))
  const [note, setNote]         = useState('')
  const push  = useCreateAccountTrade()
  const toast = useToast()

  async function submit() {
    if (!acctId) { toast('Select an account', 'err'); return }
    const legs = rec.legs.map((l, i) => {
      const leg = { side: l.side, type: l.instrument_type, lots: parseInt(legData[i].lots), price: parseFloat(legData[i].price) }
      if (l.instrument_key) leg.instrument_key = l.instrument_key
      if (l.strike)         leg.strike         = l.strike
      if (l.expiry_str)     leg.expiry         = l.expiry_str
      if (l.lot_size)       leg.lot_size       = l.lot_size
      return leg
    })
    const res = await push.mutateAsync({ recommended_trade_id: rec.id, account_id: parseInt(acctId), symbol: rec.symbol, legs, note })
    if (res.ok) { toast('Added to account — Telegram alert sent ✓', 'ok'); onClose() }
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="inline-action action-push">
      <h4>Push to Account</h4>
      <div className="form-row">
        <label>Account</label>
        <select value={acctId} onChange={e => setAcctId(e.target.value)}>
          <option value="">Select account…</option>
          {accounts.map(a => <option key={a.id} value={a.id}>{a.label || [a.user_name, a.broker].filter(Boolean).join(' · ')}</option>)}
        </select>
      </div>
      {rec.legs.map((l, i) => {
        const strike = l.strike ? `${Number(l.strike).toLocaleString('en-IN')} ` : ''
        return (
          <div key={i} style={{display:'grid',gridTemplateColumns:'1fr 70px 100px',gap:8,alignItems:'end',marginBottom:8}}>
            <div style={{display:'flex',gap:8}}>
              <span className={l.side === 'BUY' ? 'side-buy' : 'side-sell'} style={{fontWeight:700,fontSize:12}}>{l.side}</span>
              <div>
                <div style={{fontSize:13,fontWeight:700}}>{l.symbol || rec.symbol}</div>
                <div style={{fontSize:11,color:'var(--muted)'}}>{strike}{l.instrument_type}{l.expiry_str ? ` · ${l.expiry_str}` : ''}</div>
              </div>
            </div>
            <div>
              <label>Lots</label>
              <input type="number" value={legData[i].lots}
                     onChange={e => setLegData(ld => ld.map((d, j) => j === i ? { ...d, lots: e.target.value } : d))} />
            </div>
            <div>
              <label>Price</label>
              <input type="number" step="0.05" value={legData[i].price}
                     onChange={e => setLegData(ld => ld.map((d, j) => j === i ? { ...d, price: e.target.value } : d))} />
            </div>
          </div>
        )
      })}
      <div className="form-row" style={{marginTop:6}}>
        <label>Note</label>
        <input placeholder="Optional" value={note} onChange={e => setNote(e.target.value)} />
      </div>
      <div style={{display:'flex',gap:8,marginTop:8}}>
        <button className="btn btn-success btn-sm" onClick={submit} disabled={push.isPending}>Confirm Push</button>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}

// ─── Single recommendation item ───────────────────────────────────────────────

function RecItem({ rec, prices }) {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const toast   = useToast()

  const [adjOpen,  setAdjOpen]  = useState(false)
  const [exitOpen, setExitOpen] = useState(false)
  const [pushOpen, setPushOpen] = useState(false)
  const [adjLegs,  setAdjLegs]  = useState([newLeg()])
  const [adjNote,  setAdjNote]  = useState('')
  const [exitPx,   setExitPx]   = useState((rec.current_legs || rec.legs || []).map(() => ''))

  const doAdj  = useAdjustRec(rec.id)
  const doExit = useExitRec(rec.id)
  const doDel  = useDeleteRec()
  const isOpen = rec.status === 'open'

  let totalPnl = null
  if (rec.status === 'exited' && rec.exit_legs?.length) {
    let total = 0, has = false
    rec.legs.forEach((e, i) => {
      const x = rec.exit_legs[i]
      if (e.price != null && x?.price != null) {
        const qty = (e.lots || 0) * (e.lot_size || 1)
        total += e.side === 'SELL' ? (e.price - x.price) * qty : (x.price - e.price) * qty
        has = true
      }
    })
    if (has) totalPnl = total
  }

  // Compute unrealized P&L from live prices for open recs
  let unrealisedPnl = null
  if (isOpen && prices) {
    const allLegs = [...(rec.legs || []), ...(rec.adjustments || []).flatMap(a => a.legs || [])]
    let net = 0, allKnown = true
    for (const l of allLegs) {
      const ltp = l.instrument_key && prices[l.instrument_key]
      if (!ltp) { allKnown = false; break }
      const qty = (l.lots || 0) * (l.lot_size || 1)
      net += l.side === 'SELL' ? (l.price - ltp) * qty : (ltp - l.price) * qty
    }
    if (allKnown) unrealisedPnl = net
  }

  async function submitAdj() {
    const data = collectLegs(adjLegs, toast)
    if (!data) return
    const res = await doAdj.mutateAsync({ note: adjNote, legs: data.legs })
    if (res.ok) { toast('Adjustment applied — Telegram alert sent ✓', 'ok'); setAdjOpen(false); setAdjLegs([newLeg()]); setAdjNote('') }
    else toast(res.error || 'Failed', 'err')
  }

  async function submitExit() {
    const legs   = rec.current_legs || rec.legs || []
    const prices = exitPx.slice(0, legs.length).map(parseFloat)
    if (prices.some(p => !p || p <= 0)) { toast('Enter valid exit price for each leg', 'err'); return }
    const res = await doExit.mutateAsync({ prices })
    if (res.ok) { toast('Exit signal sent ✓', 'ok'); setExitOpen(false) }
    else toast(res.error || 'Failed', 'err')
  }

  async function submitDel() {
    if (!confirm('Delete this recommendation?')) return
    const res = await doDel.mutateAsync(rec.id)
    if (res.ok) toast('Recommendation deleted', 'ok')
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="rec-item">
      <div className="rec-header">
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <span className="rec-symbol">{rec.symbol}</span>
          <span className={`badge badge-${rec.status === 'open' ? 'open' : 'exited'}`}>{rec.status === 'open' ? 'Open' : rec.status}</span>
          {rec.adj_count > 0 && <span style={{fontSize:11,padding:'2px 7px',borderRadius:20,background:'#fef9c3',color:'#854d0e',fontWeight:600}}>{rec.adj_count} adj</span>}
        </div>
        <div style={{fontSize:11,color:'var(--muted)',marginTop:4}}>
          Open: {rec.entry_ist}{rec.exit_ist ? <> &nbsp;·&nbsp; Exited: {rec.exit_ist}</> : null}
        </div>
      </div>

      <RecLegs rec={rec} />

      {/* P&L bars */}
      {isOpen && rec.margin_required && (
        <div className="pnl-bar">
          <span className="pnl-bar-lbl">Margin</span>
          <span style={{fontWeight:700}}>₹{Math.round(rec.margin_required).toLocaleString('en-IN')}</span>
        </div>
      )}
      {isOpen && (
        <div className="pnl-bar">
          <span className="pnl-bar-lbl">Unrealised P&amp;L</span>
          {unrealisedPnl != null
            ? <span style={{display:'flex',alignItems:'center',gap:4}}>
                <span style={{fontWeight:700,color:unrealisedPnl>=0?'var(--green)':'var(--red)'}}>{fmtPnl(unrealisedPnl)}</span>
                {rec.margin_required && <span style={{fontSize:11,fontWeight:600,color:unrealisedPnl>=0?'var(--green)':'var(--red)'}}>
                  ({unrealisedPnl>=0?'+':''}{((unrealisedPnl/rec.margin_required)*100).toFixed(1)}%)
                </span>}
              </span>
            : <span className="pnl-neu" style={{fontWeight:700}}>—</span>
          }
        </div>
      )}
      {!isOpen && totalPnl != null && (
        <div className="pnl-bar">
          <span className="pnl-bar-lbl">Realized P&amp;L</span>
          <span style={{display:'flex',alignItems:'center',gap:4}}>
            <span style={{fontWeight:700,color:totalPnl>=0?'var(--green)':'var(--red)'}}>{fmtPnl(totalPnl)}</span>
            {rec.margin_required && <span style={{fontSize:11,fontWeight:600,color:totalPnl>=0?'var(--green)':'var(--red)'}}>
              ({totalPnl>=0?'+':''}{((totalPnl/rec.margin_required)*100).toFixed(1)}%)
            </span>}
          </span>
        </div>
      )}

      {/* Admin actions */}
      {isAdmin && isOpen && <>
        <div style={{display:'flex',gap:8,padding:'8px 14px',borderTop:'1px solid var(--border)',background:'#fafafa',flexWrap:'wrap'}}>
          <button className="btn btn-primary btn-sm" onClick={() => { setAdjOpen(v=>!v); setExitOpen(false) }}>Adjust</button>
          <button className="btn btn-danger btn-sm"  onClick={() => { setExitOpen(v=>!v); setAdjOpen(false) }}>Exit</button>
          <button className="btn btn-ghost btn-sm"   style={{color:'var(--red)',borderColor:'#fca5a5'}} onClick={submitDel}>Delete</button>
        </div>

        {adjOpen && (
          <div className="inline-action action-adj">
            <h4>Adjust Trade</h4>
            <div style={{fontSize:11,color:'var(--muted)',marginBottom:8}}>Add legs as you'd execute them — SELL to reduce, BUY to add.</div>
            <LegBuilder legs={adjLegs} onChange={setAdjLegs} />
            <div className="form-row" style={{marginTop:10}}>
              <label>Note (optional)</label>
              <input placeholder="e.g. Rolling May → Jun" value={adjNote} onChange={e=>setAdjNote(e.target.value)} />
            </div>
            <div style={{display:'flex',gap:8,marginTop:10}}>
              <button className="btn btn-primary btn-sm" onClick={submitAdj} disabled={doAdj.isPending}>Apply Adjustment</button>
              <button className="btn btn-ghost btn-sm" onClick={() => setAdjOpen(false)}>Cancel</button>
            </div>
          </div>
        )}

        {exitOpen && (
          <div className="inline-action action-exit">
            <h4>Exit Trade</h4>
            {(rec.current_legs || rec.legs || []).map((l, i) => {
              const exitSide = l.side === 'BUY' ? 'SELL' : 'BUY'
              const strike   = l.strike ? `${Number(l.strike).toLocaleString('en-IN')} ` : ''
              return (
                <div key={i} style={{display:'grid',gridTemplateColumns:'1fr 130px',gap:10,alignItems:'center',marginBottom:8}}>
                  <div style={{display:'flex',gap:8}}>
                    <span className={exitSide==='BUY'?'side-buy':'side-sell'} style={{fontWeight:700}}>{exitSide}</span>
                    <div>
                      <div style={{fontSize:13,fontWeight:700,color:'#1e293b'}}>{l.symbol || rec.symbol}</div>
                      <div style={{fontSize:11,color:'var(--muted)'}}>{strike}{l.instrument_type}{l.expiry_str?` · ${l.expiry_str}`:''} · {fmtQty(l.lots,l.lot_size,l.instrument_type)} @{fmtRs(l.price,2)}</div>
                    </div>
                  </div>
                  <div>
                    <label>Price</label>
                    <input type="number" step="0.05" placeholder="0.00"
                           value={exitPx[i]||''} onChange={e=>setExitPx(ps=>ps.map((p,j)=>j===i?e.target.value:p))} />
                  </div>
                </div>
              )
            })}
            <div style={{display:'flex',gap:8}}>
              <button className="btn btn-danger btn-sm" onClick={submitExit} disabled={doExit.isPending}>Confirm Exit</button>
              <button className="btn btn-ghost btn-sm" onClick={()=>setExitOpen(false)}>Cancel</button>
            </div>
          </div>
        )}
      </>}

      {/* Client: push / adj-locked notice */}
      {!isAdmin && isOpen && (
        rec.adj_count > 0 ? (
          <div style={{margin:'10px 14px 12px',padding:'10px 14px',background:'#eff6ff',border:'1px solid #bfdbfe',borderRadius:8,display:'flex',alignItems:'flex-start',gap:10}}>
            <span style={{fontSize:18}}>ℹ️</span>
            <div>
              <div style={{fontSize:12,fontWeight:700,color:'#1d4ed8',marginBottom:2}}>New entries not available</div>
              <div style={{fontSize:12,color:'#1e40af',lineHeight:1.5}}>This trade has been adjusted. Please contact your advisor to join the current position.</div>
            </div>
          </div>
        ) : <>
          <div style={{display:'flex',gap:8,padding:'8px 14px',borderTop:'1px solid var(--border)',background:'#fafafa'}}>
            <button className="btn btn-success btn-sm" onClick={() => setPushOpen(v=>!v)}>+ Add to Account</button>
          </div>
          {pushOpen && <PushForm rec={rec} prices={prices} onClose={() => setPushOpen(false)} />}
        </>
      )}
    </div>
  )
}

// ─── Recommendations panel (left column) ─────────────────────────────────────

const SEGMENTS = ['all', 'F&O', 'Equity', 'ETF', 'Commodities']

function RecsPanel({ isAdmin, openDrawer }) {
  const [status,  setStatus]  = useState('open')
  const [segment, setSegment] = useState('all')
  const { data: allRecs = [], isLoading, refetch } = useRecs()
  const { data: accounts = [] } = useAccounts()

  // Client-side status filter (Flask returns all recs; ignores ?status= param)
  const recs = status === 'all'    ? allRecs :
               status === 'exited' ? allRecs.filter(r => r.status !== 'open') :
                                     allRecs.filter(r => r.status === 'open')

  const usedSegs = new Set(allRecs.map(r => r.segment))
  const filtered = segment === 'all' ? recs : recs.filter(r => r.segment === segment)

  // Poll live LTPs for open rec legs
  const instrKeys = [...new Set(
    allRecs.filter(r => r.status === 'open')
           .flatMap(r => (r.current_legs || r.legs || []).map(l => l.instrument_key).filter(Boolean))
  )]
  const { data: prices = {} } = useRecPrices(instrKeys)

  return (
    <div>
      {isAdmin && <CreateRecForm />}

      {/* Client setup banner */}
      {!isAdmin && accounts.length === 0 && (
        <div className="card">
          <div className="card-body" style={{textAlign:'center',padding:'28px 20px'}}>
            <div style={{fontSize:28,marginBottom:10}}>🏦</div>
            <div style={{fontSize:14,fontWeight:700,marginBottom:6}}>Set up your accounts</div>
            <div style={{fontSize:13,color:'var(--muted)',marginBottom:18}}>Add your brokerage accounts to start pushing trades from recommendations.</div>
            <button className="btn btn-primary" onClick={openDrawer}>Open Account Settings →</button>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h2>Recommended Positions</h2>
          <select style={{width:'auto',fontSize:12,padding:'4px 8px',marginLeft:12}}
                  value={status} onChange={e => setStatus(e.target.value)}>
            <option value="open">Open</option>
            <option value="exited">Exited</option>
            <option value="all">All</option>
          </select>
          <button className="btn btn-ghost btn-sm" style={{marginLeft:'auto'}} onClick={refetch}>↻</button>
        </div>

        <div style={{display:'flex',gap:6,flexWrap:'wrap',padding:'8px 10px 6px',borderBottom:'1px solid var(--border)',background:'#fafafa'}}>
          {SEGMENTS.filter(s => s === 'all' || usedSegs.has(s)).map(s => (
            <button key={s} className={`seg-chip${segment===s?' active':''}`} onClick={() => setSegment(s)}>
              {s === 'all' ? 'All' : s}
            </button>
          ))}
        </div>

        <div className="card-body" style={{padding:10}}>
          {isLoading && <div className="empty">Loading…</div>}
          {!isLoading && !filtered.length && (
            <div className="empty">No {segment !== 'all' ? segment + ' ' : ''}{status !== 'all' ? status + ' ' : ''}recommendations.</div>
          )}
          {filtered.map(r => <RecItem key={r.id} rec={r} prices={prices} />)}
        </div>
      </div>
    </div>
  )
}

// ─── Pending adj section (inside trade card, client applies) ─────────────────

const ADJ_TYPE_LABEL = { auto_roll:'Auto Roll', replace_legs:'Replace Legs', add_legs:'Add Legs', partial_exit:'Partial Exit', exit:'Full Exit', adjustment:'Adjustment' }

function PendingAdjSection({ trade }) {
  const [prices, setPrices] = useState({})
  const doApply = useApplyAdjTrade(trade.id)
  const toast   = useToast()

  async function applyAdj(a) {
    const legs = []
    for (let i = 0; i < (a.legs || []).length; i++) {
      const price = parseFloat(prices[`${a.id}-${i}`] || '')
      if (!price || price <= 0) { toast(`Enter price for leg ${i+1}`, 'err'); return }
      const rl = a.legs[i]
      legs.push({ action:'entry', side:rl.side, instrument_type:rl.instrument_type,
                  instrument_key:rl.instrument_key, strike:rl.strike, expiry_str:rl.expiry_str,
                  lots:rl.lots, lot_size:rl.lot_size, price })
    }
    const res = await doApply.mutateAsync({ adjustment_id: a.id, adj_type: a.adj_type, legs })
    if (res.ok) toast('Adjustment applied to your position ✓', 'ok')
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="pending-adj-banner">
      <div style={{fontWeight:700,fontSize:11,textTransform:'uppercase',letterSpacing:.4,marginBottom:6,color:'#92400e'}}>
        Pending Adjustments — apply to your position
      </div>
      {trade.pending_adjustments.map(a => (
        <div key={a.id} style={{border:'1px solid #fde68a',borderRadius:6,marginBottom:8,overflow:'hidden'}}>
          <div style={{padding:'6px 10px',background:'#fef3c7',display:'flex',gap:8,alignItems:'center'}}>
            <span style={{fontSize:10,fontWeight:700,padding:'2px 6px',borderRadius:10,background:'#e0e7ff',color:'#3730a3'}}>{ADJ_TYPE_LABEL[a.adj_type]||a.adj_type}</span>
            {a.note && <span style={{fontSize:11,color:'#92400e'}}>{a.note}</span>}
          </div>
          <div style={{padding:10,background:'#fff'}}>
            {(a.legs||[]).map((l,i) => {
              const st = l.strike ? `${Number(l.strike).toLocaleString('en-IN')} ` : ''
              return (
                <div key={i} style={{display:'grid',gridTemplateColumns:'1fr 120px',gap:8,alignItems:'center',marginBottom:6}}>
                  <div>
                    <span className={l.side==='BUY'?'side-buy':'side-sell'} style={{fontWeight:700}}>{l.side}</span>
                    &nbsp;{st}{l.instrument_type} · {fmtQty(l.lots,l.lot_size,l.instrument_type)}
                    <div style={{fontSize:10,color:'var(--muted)'}}>Rec @ {fmtRs(l.price,2)}</div>
                  </div>
                  <div>
                    <label>Your price</label>
                    <input type="number" step="0.05" placeholder="0.00"
                           value={prices[`${a.id}-${i}`]||''}
                           onChange={e => setPrices(p => ({...p,[`${a.id}-${i}`]:e.target.value}))} />
                  </div>
                </div>
              )
            })}
            <button className="btn btn-primary btn-sm" onClick={() => applyAdj(a)} disabled={doApply.isPending}>
              Apply to My Position
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Account position trade card ─────────────────────────────────────────────

function TradeCard({ trade: t, isAdmin, prices }) {
  const [exitOpen, setExitOpen] = useState(false)
  const [exitPx,   setExitPx]   = useState((t.current_legs || t.legs || []).map(() => ''))
  const [exitNote, setExitNote] = useState('')
  const doExit = useExitTrade(t.id)
  const doDel  = useDeleteTrade()
  const toast  = useToast()

  async function submitExit() {
    const legs   = t.current_legs || t.legs || []
    const exitPrices = exitPx.slice(0, legs.length).map(parseFloat)
    if (exitPrices.some(p => !p || p <= 0)) { toast('Enter valid exit price for each leg', 'err'); return }
    const res = await doExit.mutateAsync({ prices: exitPrices, note: exitNote })
    if (res.ok) { toast('Trade closed — Telegram alert sent ✓', 'ok'); setExitOpen(false) }
    else toast(res.error || 'Exit failed', 'err')
  }

  async function handleDel() {
    if (!confirm('Delete this trade? This cannot be undone.')) return
    const res = await doDel.mutateAsync(t.id)
    if (res.ok) toast('Trade deleted ✓', 'ok')
    else toast(res.error || 'Failed', 'err')
  }

  const mkLegRows = (legs, bg) => legs.map((l, i) => {
    const sc         = l.side === 'BUY' ? 'side-buy' : 'side-sell'
    const strike     = l.strike ? `${Number(l.strike).toLocaleString('en-IN')} ` : ''
    const exp        = l.expiry_str ? ` ${l.expiry_str}` : ''
    const instrument = l.instrument_type === 'EQ' ? t.symbol : `${strike}${l.instrument_type}${exp}`
    const ltp        = prices && l.instrument_key ? prices[l.instrument_key] : null
    const qty        = (l.lots || 0) * (l.lot_size || 1)
    const legPnl     = ltp != null && l.price != null
      ? (l.side === 'SELL' ? (l.price - ltp) * qty : (ltp - l.price) * qty)
      : null
    const bgStyle = bg ? {background:bg} : {}
    return (
      <tr key={i} style={bgStyle}>
        <td className={sc}>{l.side}</td>
        <td>{instrument}</td>
        <td>{fmtQty(l.lots, l.lot_size, l.instrument_type)}</td>
        <td>{fmtRs(l.price, 2)}</td>
        <td className="ltp-cell" style={bgStyle}>{ltp != null ? fmtRs(ltp, 2) : '—'}</td>
        <td style={bgStyle} className={legPnl != null ? (legPnl >= 0 ? 'pnl-pos' : 'pnl-neg') : 'pnl-neu'}>
          {legPnl != null ? fmtPnl(legPnl) : '—'}
        </td>
      </tr>
    )
  })

  return (
    <div style={{border:'1px solid var(--border)',borderRadius:8,marginBottom:12,overflow:'hidden',background:'#fff'}}>
      <div style={{padding:'9px 14px',background:'#f8fafc',display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
        <span style={{fontWeight:700,fontSize:14}}>{t.symbol}</span>
        <span className="badge badge-open">Open</span>
        {t.pending_adj_count > 0 && (
          <span style={{fontSize:11,padding:'2px 7px',borderRadius:20,background:'#fef3c7',color:'#92400e',fontWeight:600}}>⚠ {t.pending_adj_count} adj pending</span>
        )}
        <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,background:'#f1f5f9',color:'var(--muted)',border:'1px solid var(--border)'}}>{t.account_label}</span>
        <span style={{fontSize:11,color:'var(--muted)',marginLeft:'auto'}}>{t.entry_ist}</span>
      </div>

      <table className="legs-table">
        <thead><tr><th>Side</th><th>Instrument</th><th>Qty</th><th>Entry</th><th>LTP</th><th>P&amp;L</th></tr></thead>
        <tbody>
          <tr style={{background:'#f8fafc'}}>
            <td colSpan={6} style={{padding:'4px 12px 2px',borderBottom:'none',fontSize:10,fontWeight:600,color:'var(--muted)',textTransform:'uppercase',letterSpacing:.5}}>Entry</td>
          </tr>
          {mkLegRows(t.legs, '#f8fafc')}
          {(t.applied_adjustments||[]).map((a, ai) => {
            const bg = ADJ_COLORS[ai % ADJ_COLORS.length]
            return [
              <tr key={`ah-${a.id}`} style={{background:bg}}>
                <td colSpan={6} style={{padding:'4px 12px 2px',borderBottom:'none',fontSize:10,fontWeight:600,color:'var(--muted)',textTransform:'uppercase',letterSpacing:.5,borderTop:'1px solid #f1f5f9'}}>
                  Adjustment {ai+1}{a.note?` · ${a.note}`:''}
                </td>
              </tr>,
              ...mkLegRows(a.legs||[], bg)
            ]
          })}
        </tbody>
      </table>

      {(() => {
        let net = 0, allKnown = true
        const allLegs = [...(t.legs || []), ...(t.applied_adjustments || []).flatMap(a => a.legs || [])]
        for (const l of allLegs) {
          const ltp = prices && l.instrument_key && prices[l.instrument_key]
          if (!ltp) { allKnown = false; break }
          const qty = (l.lots || 0) * (l.lot_size || 1)
          net += l.side === 'SELL' ? (l.price - ltp) * qty : (ltp - l.price) * qty
        }
        return (
          <div className="pnl-bar">
            <span className="pnl-bar-lbl">Unrealised P&amp;L</span>
            {allKnown
              ? <span style={{fontWeight:700,color:net>=0?'var(--green)':'var(--red)'}}>{fmtPnl(net)}</span>
              : <span className="pnl-neu" style={{fontWeight:700}}>—</span>
            }
          </div>
        )
      })()}

      {(t.pending_adjustments||[]).length > 0 && <PendingAdjSection trade={t} />}

      {!isAdmin && <>
        <div style={{padding:'8px 14px',borderTop:'1px solid var(--border)',display:'flex',gap:8}}>
          <button className="btn btn-danger btn-sm" onClick={() => setExitOpen(v=>!v)}>Exit Trade</button>
          <button className="btn btn-ghost btn-sm" style={{color:'var(--red)',borderColor:'#fca5a5'}} onClick={handleDel}>Delete</button>
        </div>
        {exitOpen && (
          <div className="inline-action action-exit">
            <h4>Exit Trade</h4>
            {(t.current_legs||t.legs||[]).map((l,i) => {
              const strike = l.strike ? `${Number(l.strike).toLocaleString('en-IN')} ` : ''
              return (
                <div key={i} style={{display:'grid',gridTemplateColumns:'1fr 130px',gap:10,alignItems:'center',marginBottom:8}}>
                  <div>
                    <span className={l.side==='BUY'?'side-buy':'side-sell'} style={{fontWeight:700}}>{l.side}</span>
                    &nbsp;{strike}{l.instrument_type} · {fmtQty(l.lots,l.lot_size,l.instrument_type)}
                    <div style={{fontSize:11,color:'var(--muted)',marginTop:2}}>entry {fmtRs(l.price,2)}</div>
                  </div>
                  <div>
                    <label>Price</label>
                    <input type="number" step="0.05" placeholder="0.00"
                           value={exitPx[i]||''} onChange={e=>setExitPx(ps=>ps.map((p,j)=>j===i?e.target.value:p))} />
                  </div>
                </div>
              )
            })}
            <div style={{display:'flex',gap:8,marginTop:12,alignItems:'center'}}>
              <div style={{flex:1}}>
                <input placeholder="Note (optional)" value={exitNote} onChange={e=>setExitNote(e.target.value)} />
              </div>
              <button className="btn btn-danger btn-sm" onClick={submitExit} disabled={doExit.isPending}>Confirm Exit</button>
              <button className="btn btn-ghost btn-sm" onClick={()=>setExitOpen(false)}>Cancel</button>
            </div>
          </div>
        )}
      </>}
    </div>
  )
}

// ─── Trade history card ────────────────────────────────────────────────────────

function HistoryCard({ trade: t }) {
  const pnl    = t.realized_pnl || 0
  const pnlCls = pnl > 0 ? 'pnl-pos' : pnl < 0 ? 'pnl-neg' : 'pnl-neu'

  const origLegs  = (t.entry_legs||[]).filter(l => !l.adjustment_id)
  const adjGroups = []
  ;(t.entry_legs||[]).filter(l => l.adjustment_id).forEach(l => {
    let g = adjGroups.find(g => g.adj_id === l.adjustment_id)
    if (!g) { g = { adj_id: l.adjustment_id, legs: [] }; adjGroups.push(g) }
    g.legs.push(l)
  })

  const mkRow = (entry, exitLeg, bg) => {
    const sc         = entry.side === 'BUY' ? 'side-buy' : 'side-sell'
    const strike     = entry.strike ? `${Number(entry.strike).toLocaleString('en-IN')} ` : ''
    const instrument = entry.instrument_type === 'EQ' ? t.symbol : `${strike}${entry.instrument_type}`
    const legPnl = (entry.price != null && exitLeg?.price != null)
      ? (() => { const qty=(entry.lots||0)*(entry.lot_size||1); return entry.side==='SELL'?(entry.price-exitLeg.price)*qty:(exitLeg.price-entry.price)*qty })()
      : null
    return (
      <tr key={`${entry.id}`} style={bg?{background:bg}:{}}>
        <td className={sc}>{entry.side}</td>
        <td>{instrument}</td>
        <td>{fmtQty(entry.lots, entry.lot_size, entry.instrument_type)}</td>
        <td>{fmtRs(entry.price, 2)}</td>
        <td>{exitLeg?.price != null ? fmtRs(exitLeg.price, 2) : '—'}</td>
        <td>{legPnl!=null?<span style={{color:legPnl>=0?'var(--green)':'var(--red)',fontWeight:600}}>{fmtPnl(legPnl)}</span>:'—'}</td>
      </tr>
    )
  }

  // Pre-compute exit leg pairings
  const origLen = origLegs.length
  const adjOffsets = adjGroups.map((_, ai) =>
    origLen + adjGroups.slice(0, ai).reduce((s, g2) => s + g2.legs.length, 0)
  )

  return (
    <div style={{border:'1px solid var(--border)',borderRadius:8,marginBottom:12,overflow:'hidden',background:'#fff'}}>
      <div style={{padding:'9px 14px',background:'#f8fafc',display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
        <span style={{fontWeight:700,fontSize:14}}>{t.symbol}</span>
        <span className="badge badge-exited">Closed</span>
        <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,background:'#f1f5f9',color:'var(--muted)',border:'1px solid var(--border)'}}>{t.account_label}</span>
        <span style={{fontSize:11,color:'var(--muted)',marginLeft:'auto',display:'flex',flexDirection:'column',alignItems:'flex-end',gap:1}}>
          <span>In: {t.entry_ist}</span><span>Out: {t.exit_ist}</span>
        </span>
      </div>
      <table className="legs-table">
        <thead><tr><th>Side</th><th>Instrument</th><th>Qty</th><th>Entry</th><th>Exit</th><th>P&amp;L</th></tr></thead>
        <tbody>
          <tr style={{background:'#f8fafc'}}>
            <td colSpan={6} style={{padding:'4px 14px 2px',borderBottom:'none',fontSize:10,fontWeight:600,color:'var(--muted)',textTransform:'uppercase',letterSpacing:.5}}>Entry</td>
          </tr>
          {origLegs.map((e, i) => mkRow(e, t.exit_legs?.[i], '#f8fafc'))}
          {adjGroups.map((g, ai) => {
            const bg     = ADJ_COLORS[ai % ADJ_COLORS.length]
            const offset = adjOffsets[ai]
            return [
              <tr key={`ah-${g.adj_id}`} style={{background:bg}}>
                <td colSpan={6} style={{padding:'4px 14px 2px',borderBottom:'none',fontSize:10,fontWeight:600,color:'var(--muted)',textTransform:'uppercase',letterSpacing:.5,borderTop:'1px solid #f1f5f9'}}>Adjustment {ai+1}</td>
              </tr>,
              ...g.legs.map((e, j) => mkRow(e, t.exit_legs?.[offset + j], bg))
            ]
          })}
        </tbody>
      </table>
      <div className="pnl-bar">
        <span className="pnl-bar-lbl">Realized P&amp;L</span>
        <span className={pnlCls} style={{fontWeight:700}}>{fmtPnl(pnl)}</span>
      </div>
    </div>
  )
}

// ─── Positions / history panel (right column) ────────────────────────────────

function TradesPanel({ isAdmin }) {
  const [posTab, setPosTab]   = useState('open')
  const [acctFilter, setAcctFilter] = useState('')
  const { data: accounts = [] }     = useAccounts()

  const params   = acctFilter ? { account_id: acctFilter } : undefined
  const { data: trades = [], isLoading, refetch }  = useTrades(params)
  const { data: history = [], isLoading: histLoad, refetch: refetchHist } = useTradeHistory(params, posTab === 'history')

  const instrKeys = [...new Set(trades.flatMap(t => {
    const allLegs = [...(t.legs || []), ...(t.applied_adjustments || []).flatMap(a => a.legs || [])]
    return allLegs.map(l => l.instrument_key).filter(Boolean)
  }))]
  const { data: prices = {} } = useRecPrices(instrKeys)

  const title = isAdmin ? 'All Positions' : 'My Positions'

  return (
    <div>
      <div className="card">
        <div className="card-header" style={{gap:0}}>
          <div style={{display:'flex',gap:2}}>
            <button className={`pos-tab${posTab==='open'?' active':''}`} onClick={()=>setPosTab('open')}>{title}</button>
            <button className={`pos-tab${posTab==='history'?' active':''}`} onClick={()=>setPosTab('history')}>Trade History</button>
          </div>
          <select value={acctFilter} onChange={e=>setAcctFilter(e.target.value)}
                  style={{width:'auto',fontSize:12,padding:'4px 8px',marginLeft:'auto'}}>
            <option value="">All Accounts</option>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.label||a.account_no||`Account ${a.id}`}</option>)}
          </select>
          <button className="btn btn-ghost btn-sm" onClick={()=>posTab==='open'?refetch():refetchHist()}>↻</button>
        </div>
        <div className="card-body" style={{padding:10}}>
          {posTab === 'open' && (
            isLoading ? <div className="empty">Loading…</div> :
            !trades.length ? <div className="empty">No open account positions.</div> :
            trades.map(t => <TradeCard key={t.id} trade={t} isAdmin={isAdmin} prices={prices} />)
          )}
          {posTab === 'history' && (
            histLoad ? <div className="empty">Loading…</div> :
            !history.length ? <div className="empty">No closed trades.</div> :
            history.map(t => <HistoryCard key={t.id} trade={t} />)
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function Dashboard({ openDrawer }) {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'

  return (
    <div className="dash-layout">
      <RecsPanel isAdmin={isAdmin} openDrawer={openDrawer} />
      <TradesPanel isAdmin={isAdmin} />
    </div>
  )
}
