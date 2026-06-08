import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useRecs, useRecPrices, useCreateRec, useDeleteRec, useExitRec, useAdjustRec, useCreateAccountTrade,
         useTrades, useTradeHistory, useExitTrade, useApplyAdjTrade, useDeleteTrade,
         useAccounts, useAccountPortfolio } from '../hooks/useTrades'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCredits, getPlans, subscribeWithCredits, listGames, submitEntry, getPortfolio } from '../api/games'
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
      <button style={{width:'100%',padding:8,border:'1.5px dashed #cbd5e1',borderRadius:6,background:'none',color:'var(--muted)',cursor:'pointer',fontSize:13,marginTop:2}}
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
    if (!note.trim()) { toast('Title is required', 'err'); return }
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
        <div className="form-row" style={{marginBottom:12}}>
          <label>Title <span style={{color:'var(--red)'}}>*</span></label>
          <input placeholder="e.g. Bull put spread on Nifty" value={note} onChange={e => setNote(e.target.value)} />
        </div>
        <LegBuilder legs={legs} onChange={setLegs} />
        <button className="btn btn-primary" style={{width:'100%',justifyContent:'center',marginTop:16}}
                onClick={submit} disabled={create.isPending}>
          Create &amp; Send Alert
        </button>
      </div>
    </div>
  )
}

// ─── Shared: P&L bar ─────────────────────────────────────────────────────────

function PnlBar({ label, value, base }) {
  const color = value != null ? (value >= 0 ? 'var(--green)' : 'var(--red)') : null
  return (
    <div className="pnl-bar">
      <span className="pnl-bar-lbl">{label}</span>
      {value != null
        ? <span style={{display:'flex',alignItems:'center',gap:4}}>
            <span style={{fontWeight:700,color}}>{fmtPnl(value)}</span>
            {base > 0 && <span style={{fontSize:11,fontWeight:600,color}}>({value>=0?'+':''}{((value/base)*100).toFixed(1)}%)</span>}
          </span>
        : <span className="pnl-neu" style={{fontWeight:700}}>—</span>
      }
    </div>
  )
}

// ─── Leg display ─────────────────────────────────────────────────────────────

function fmtContract(l) {
  return [l.strike ? Number(l.strike).toLocaleString('en-IN') : null, l.instrument_type, l.expiry_str]
    .filter(Boolean).join(' ')
}

function OpenLeg({ leg: l, symbol, prices }) {
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

function ExitedLeg({ entry: e, exitLeg: x, symbol }) {
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

function LegGroup({ title, note, legs, symbol, type = 'entry', exitLegs, exitOffset = 0, prices }) {
  return (
    <div className={`leg-group leg-group-${type}`}>
      {(title || note) && (
        <div className="leg-grp-hdr">
          {title}
          {note && <span className="leg-grp-note">{note}</span>}
        </div>
      )}
      {legs.map((l, i) =>
        exitLegs
          ? <ExitedLeg key={i} entry={l} exitLeg={exitLegs[exitOffset + i]} symbol={symbol} />
          : <OpenLeg   key={i} leg={l} symbol={symbol} prices={prices} />
      )}
    </div>
  )
}

function RecLegs({ rec, prices }) {
  const exitLegs = rec.status === 'exited' ? rec.exit_legs : null
  const adjs     = rec.adjustments || []

  return (
    <div className="rec-legs">
      <LegGroup type="entry" title="Entry"
        legs={rec.legs} symbol={rec.symbol} exitLegs={exitLegs} prices={prices} />

      {adjs.map((a, ai) => {
        const offset = exitLegs
          ? rec.legs.length + adjs.slice(0, ai).reduce((s, a2) => s + (a2.legs?.length || 0), 0)
          : 0
        return (
          <div key={a.id || ai}>
            <div className="adj-connector">↓ Adjustment {ai + 1}</div>
            <LegGroup type="adj" note={a.note}
              legs={a.legs || []} symbol={rec.symbol} exitLegs={exitLegs} exitOffset={offset} prices={prices} />
          </div>
        )
      })}

    </div>
  )
}

// ─── Push to account form (client) ───────────────────────────────────────────

function PushForm({ rec, prices, onClose, openDrawer, onPushed }) {
  const { data: allAccounts = [] } = useAccounts()
  const realAccounts = allAccounts.filter(a => !a.game_id)
  const gameAccounts = allAccounts.filter(a => a.game_id && a.game_status === 'active')
  const [acctId, setAcctId] = useState('')
  const [legData, setLegData] = useState(rec.legs.map(l => {
    const ltp = prices && l.instrument_key ? prices[l.instrument_key] : null
    return { lots: String(l.lots), price: String(ltp ?? l.price ?? '') }
  }))
  const [note, setNote] = useState('')
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
    if (res.ok) { toast('Added to account ✓', 'ok'); onPushed?.(parseInt(acctId)); onClose() }
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="inline-action action-push">
      <h4>Push to Account</h4>
      <div className="form-row">
        <label>Account</label>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <select value={acctId} onChange={e => setAcctId(e.target.value)}>
            <option value="">Select account…</option>
            {realAccounts.length > 0 && (
              <optgroup label="Broker Accounts">
                {realAccounts.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.label || [a.broker, a.account_no].filter(Boolean).join(' · ') || `Account ${a.id}`}
                  </option>
                ))}
              </optgroup>
            )}
            {gameAccounts.length > 0 && (
              <optgroup label="Game Accounts">
                {gameAccounts.map(a => <option key={a.id} value={a.id}>{a.label || `Game #${a.game_id}`}</option>)}
              </optgroup>
            )}
          </select>
          {openDrawer && <button type="button" className="add-account-link" onClick={() => openDrawer('accounts')}>+ Add</button>}
        </div>
      </div>
      {rec.legs.map((l, i) => (
        <div key={i} className="form-leg-row">
          <div className="form-leg-info">
            <span className={`leg-pill ${l.side==='BUY'?'leg-pill-buy':'leg-pill-sell'}`}>{l.side}</span>
            <div>
              <div className="rec-leg-sym">{l.symbol || rec.symbol}</div>
              {fmtContract(l) && <div className="rec-leg-contract">{fmtContract(l)}</div>}
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
      ))}
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

// ─── Admin inline forms ───────────────────────────────────────────────────────

function AdjustForm({ rec, onClose }) {
  const [legs, setLegs] = useState([newLeg()])
  const [note, setNote] = useState('')
  const doAdj = useAdjustRec(rec.id)
  const toast = useToast()

  async function submit() {
    const data = collectLegs(legs, toast)
    if (!data) return
    const res = await doAdj.mutateAsync({ note, legs: data.legs })
    if (res.ok) { toast('Adjustment applied — Telegram alert sent ✓', 'ok'); onClose() }
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="inline-action action-adj">
      <h4>Adjust Trade</h4>
      <div style={{fontSize:11,color:'var(--muted)',marginBottom:8}}>Add legs as you'd execute them — SELL to reduce, BUY to add.</div>
      <LegBuilder legs={legs} onChange={setLegs} />
      <div className="form-row" style={{marginTop:10}}>
        <label>Note (optional)</label>
        <input placeholder="e.g. Rolling May → Jun" value={note} onChange={e => setNote(e.target.value)} />
      </div>
      <div style={{display:'flex',gap:8,marginTop:10}}>
        <button className="btn btn-primary btn-sm" onClick={submit} disabled={doAdj.isPending}>Apply Adjustment</button>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}

function ExitRecForm({ rec, onClose }) {
  const legs = rec.current_legs || rec.legs || []
  const [exitPx, setExitPx] = useState(legs.map(() => ''))
  const doExit = useExitRec(rec.id)
  const toast  = useToast()

  async function submit() {
    const prices = exitPx.slice(0, legs.length).map(parseFloat)
    if (prices.some(p => !p || p <= 0)) { toast('Enter valid exit price for each leg', 'err'); return }
    const res = await doExit.mutateAsync({ prices })
    if (res.ok) { toast('Exit signal sent ✓', 'ok'); onClose() }
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="inline-action action-exit">
      <h4>Exit Trade</h4>
      {legs.map((l, i) => {
        const exitSide = l.side === 'BUY' ? 'SELL' : 'BUY'
        return (
          <div key={i} className="form-leg-row form-leg-row-exit">
            <div className="form-leg-info">
              <span className={`leg-pill ${exitSide==='BUY'?'leg-pill-buy':'leg-pill-sell'}`}>{exitSide}</span>
              <div>
                <div className="rec-leg-sym">{l.symbol || rec.symbol}</div>
                <div className="rec-leg-contract">{fmtContract(l)} · {fmtQty(l.lots,l.lot_size,l.instrument_type)} @{fmtRs(l.price,2)}</div>
              </div>
            </div>
            <div>
              <label>Price</label>
              <input type="number" step="0.05" placeholder="0.00"
                     value={exitPx[i]||''} onChange={e => setExitPx(ps => ps.map((p,j) => j===i ? e.target.value : p))} />
            </div>
          </div>
        )
      })}
      <div style={{display:'flex',gap:8}}>
        <button className="btn btn-danger btn-sm" onClick={submit} disabled={doExit.isPending}>Confirm Exit</button>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}

// ─── Single recommendation item ───────────────────────────────────────────────

function RecItem({ rec, prices, openDrawer, onPushed, highlight }) {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const toast   = useToast()

  const [collapsed, setCollapsed] = useState(!highlight)
  const [adjOpen,  setAdjOpen]  = useState(false)
  const [exitOpen, setExitOpen] = useState(false)
  const [pushOpen, setPushOpen] = useState(false)
  const doDel  = useDeleteRec()
  const isOpen = rec.status === 'open'

  // Realized P&L for exited recs — flatten original + adjustment legs to match exit_legs index
  let totalPnl = null
  if (rec.status === 'exited' && rec.exit_legs?.length) {
    const adjs = rec.adjustments || []
    const allEntryLegs = [...rec.legs, ...adjs.flatMap(a => a.legs || [])]
    let total = 0, has = false
    allEntryLegs.forEach((e, i) => {
      const x = rec.exit_legs[i]
      if (e.price != null && x?.price != null) {
        const qty = (e.lots || 0) * (e.lot_size || 1)
        total += e.side === 'SELL' ? (e.price - x.price) * qty : (x.price - e.price) * qty
        has = true
      }
    })
    if (has) totalPnl = total
  }

  // Unrealized P&L from live prices
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

  async function handleDelete() {
    if (!confirm('Delete this recommendation?')) return
    const res = await doDel.mutateAsync(rec.id)
    if (res.ok) toast('Recommendation deleted', 'ok')
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div id={`rec-${rec.id}`} className={`rec-item rec-item-${rec.status}${highlight ? ' rec-item-highlight' : ''}`}>
      {/* Header — always fully visible */}
      <div className="rec-header" style={{cursor:'pointer'}} onClick={() => setCollapsed(v => !v)}>
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
          <div style={{display:'flex',alignItems:'center',gap:7,flexWrap:'wrap',flex:1,minWidth:0}}>
            <span className="rec-symbol" style={{fontSize:15}}>{rec.note || rec.symbol}</span>
            <span className={`badge badge-${rec.status === 'open' ? 'open' : 'exited'}`}>{rec.status === 'open' ? 'Live' : rec.status}</span>
            {rec.segment && <span className="rec-seg-tag">{rec.segment}</span>}
            {rec.adj_count > 0 && <span className="adj-badge">{rec.adj_count} adj</span>}
          </div>
          <div style={{display:'flex',alignItems:'center',gap:8,flexShrink:0}}>
            {collapsed && !isOpen && totalPnl != null && (
              <span style={{fontSize:12,fontWeight:700,color:totalPnl>=0?'var(--green)':'var(--red)'}}>
                {fmtPnl(totalPnl)}
              </span>
            )}
            {collapsed && isOpen && unrealisedPnl != null && (
              <span style={{fontSize:12,fontWeight:700,color:unrealisedPnl>=0?'var(--green)':'var(--red)'}}>
                {fmtPnl(unrealisedPnl)}
              </span>
            )}
            <span className={`rec-collapse-btn${collapsed ? ' collapsed' : ''}`}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </span>
          </div>
        </div>
        <div className="rec-ts">{rec.entry_ist}{rec.exit_ist ? ` · Closed ${rec.exit_ist}` : ''}</div>
      </div>

      {/* Collapsible body */}
      <div className={`rec-body${collapsed ? ' rec-body-collapsed' : ''}`}>

      {/* Legs */}
      <RecLegs rec={rec} prices={isOpen ? prices : null} />

      {/* Stats strip */}
      {isOpen && (rec.margin_final || unrealisedPnl != null) && (
        <div className="rec-stats-strip">
          {rec.margin_final && (
            <div className="rec-stat">
              <div className="rec-stat-lbl">Margin</div>
              <div className="rec-stat-val">₹{Math.round(rec.margin_final).toLocaleString('en-IN')}</div>
            </div>
          )}
          <div className="rec-stat">
            <div className="rec-stat-lbl">Unrealised P&amp;L</div>
            <div className="rec-stat-val" style={{color: unrealisedPnl != null ? (unrealisedPnl >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--muted)'}}>
              {unrealisedPnl != null ? fmtPnl(unrealisedPnl) : '—'}
            </div>
          </div>
        </div>
      )}
      {!isOpen && totalPnl != null && (
        <div className="rec-stats-strip">
          <div className="rec-stat">
            <div className="rec-stat-lbl">Realized P&amp;L</div>
            <div className="rec-stat-val" style={{color: totalPnl >= 0 ? 'var(--green)' : 'var(--red)'}}>
              {fmtPnl(totalPnl)}
              {rec.margin_required > 0 && (
                <span style={{fontSize:11,marginLeft:5,fontWeight:600}}>
                  ({totalPnl>=0?'+':''}{((totalPnl/rec.margin_required)*100).toFixed(1)}%)
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Admin actions */}
      {isAdmin && isOpen && <>
        <div className="rec-action-bar" onClick={e => e.stopPropagation()}>
          <button className="btn btn-primary btn-sm" onClick={() => { setAdjOpen(v=>!v); setExitOpen(false) }}>Adjust</button>
          <button className="btn btn-danger btn-sm"  onClick={() => { setExitOpen(v=>!v); setAdjOpen(false) }}>Exit</button>
          <button className="btn btn-ghost btn-sm"   style={{color:'var(--red)',borderColor:'#fca5a5'}} onClick={handleDelete}>Delete</button>
        </div>
        {adjOpen  && <AdjustForm  rec={rec} onClose={() => setAdjOpen(false)} />}
        {exitOpen && <ExitRecForm rec={rec} onClose={() => setExitOpen(false)} />}
      </>}

      {/* Client actions */}
      {!isAdmin && isOpen && (
        rec.adj_count > 0
          ? <div style={{borderTop:'1px solid var(--border)',padding:'10px 14px'}}>
              <div className="rec-adj-notice" style={{margin:0}}>
                <span style={{fontSize:18}}>ℹ️</span>
                <div>
                  <div style={{fontSize:12,fontWeight:700,color:'#1d4ed8',marginBottom:2}}>New entries not available</div>
                  <div style={{fontSize:12,color:'#1e40af',lineHeight:1.5}}>This trade has been adjusted. Contact your advisor to join the current position.</div>
                </div>
              </div>
            </div>
          : <>
              <div style={{padding:'10px 14px',borderTop:'1px solid var(--border)'}} onClick={e => e.stopPropagation()}>
                <button className="btn btn-success" style={{width:'100%',justifyContent:'center',fontWeight:700,fontSize:13,padding:'9px'}}
                        onClick={() => setPushOpen(v=>!v)}>
                  {pushOpen ? 'Cancel' : '+ Add to My Account'}
                </button>
              </div>
              {pushOpen && <PushForm rec={rec} prices={prices} onClose={() => setPushOpen(false)} openDrawer={openDrawer} onPushed={onPushed} />}
            </>
      )}

      </div>
    </div>
  )
}

// ─── Recommendations panel (left column) ─────────────────────────────────────

const SEGMENTS = ['all', 'F&O', 'Equity', 'ETF', 'Commodities']

function RecsPanel({ isAdmin, openDrawer, onPushed }) {
  const [status,  setStatus]  = useState('open')
  const [segment, setSegment] = useState('all')
  const { data: allRecs = [], isLoading, refetch } = useRecs()
  const { data: accounts = [] } = useAccounts()
  const [searchParams, setSearchParams] = useSearchParams()
  const highlightId = searchParams.get('rec') ? parseInt(searchParams.get('rec')) : null

  // When recs load and ?rec= is set, switch filter to show it then scroll to it
  useEffect(() => {
    if (!highlightId || !allRecs.length) return
    const target = allRecs.find(r => r.id === highlightId)
    if (!target) return
    // Make sure the right status filter is active
    if (target.status === 'open' && status !== 'open' && status !== 'all') setStatus('open')
    if (target.status !== 'open' && status === 'open') setStatus('all')
    // Scroll after a tick so the DOM has rendered
    setTimeout(() => {
      document.getElementById(`rec-${highlightId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 100)
    // Clear the param after 3s so it doesn't linger
    const t = setTimeout(() => setSearchParams(p => { p.delete('rec'); return p }), 3000)
    return () => clearTimeout(t)
  }, [highlightId, allRecs.length])  // eslint-disable-line react-hooks/exhaustive-deps

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
            <button className="btn btn-primary" onClick={() => openDrawer('accounts')}>Open Account Settings →</button>
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
          {filtered.map(r => <RecItem key={r.id} rec={r} prices={prices} openDrawer={openDrawer} onPushed={onPushed} highlight={r.id === highlightId} />)}
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
                <div key={i} className="form-leg-row form-leg-row-exit">
                  <div className="form-leg-info">
                    <span className={`leg-pill ${l.side==='BUY'?'leg-pill-buy':'leg-pill-sell'}`}>{l.side}</span>
                    <div>
                      <div className="rec-leg-sym">{st}{l.instrument_type} · {fmtQty(l.lots,l.lot_size,l.instrument_type)}</div>
                      <div className="rec-leg-contract">Rec @ {fmtRs(l.price,2)}</div>
                    </div>
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
        <td><span className={`leg-pill ${l.side==='BUY'?'leg-pill-buy':'leg-pill-sell'}`}>{l.side}</span></td>
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
    <div className="trade-card">
      <div style={{padding:'9px 14px',background:'#f8fafc',display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
        <span style={{fontWeight:700,fontSize:14}}>{t.symbol}</span>
        <span className="badge badge-open">Open</span>
        {t.pending_adj_count > 0 && (
          <span style={{fontSize:11,padding:'2px 7px',borderRadius:20,background:'#fef3c7',color:'#92400e',fontWeight:600}}>⚠ {t.pending_adj_count} adj pending</span>
        )}
        {t.pending_exit && (
          <span style={{fontSize:11,padding:'2px 7px',borderRadius:20,background:'#fee2e2',color:'#b91c1c',fontWeight:600}}>🔔 exit pending</span>
        )}
        <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,background:'#f1f5f9',color:'var(--muted)',border:'1px solid var(--border)'}}>{t.account_label}</span>
        <span style={{fontSize:11,color:'var(--muted)',marginLeft:'auto'}}>{t.entry_ist}</span>
      </div>

      <div className="legs-table-wrap">
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
      </div>

      {t.margin != null && (
        <div className="pnl-bar">
          <span className="pnl-bar-lbl">Margin</span>
          <span style={{fontWeight:700}}>₹{Math.round(t.margin).toLocaleString('en-IN')}</span>
        </div>
      )}
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

      {t.pending_exit && (
        <div style={{padding:'10px 14px',borderTop:'2px solid #ef4444',background:'#fff1f2',display:'flex',alignItems:'flex-start',gap:10}}>
          <span style={{fontSize:16,lineHeight:1,flexShrink:0}}>🔔</span>
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontWeight:700,fontSize:12,color:'#b91c1c',textTransform:'uppercase',letterSpacing:.4,marginBottom:2}}>
              Recommendation Exited
            </div>
            <div style={{fontSize:12,color:'#7f1d1d'}}>
              The recommendation for this trade has been closed. Please exit your position.
            </div>
          </div>
          <button className="btn btn-danger btn-sm" style={{flexShrink:0}} onClick={() => setExitOpen(true)}>
            Exit Now
          </button>
        </div>
      )}

      {!isAdmin && <>
        <div style={{padding:'8px 14px',borderTop:'1px solid var(--border)',display:'flex',gap:8}}>
          <button className="btn btn-danger btn-sm" onClick={() => setExitOpen(v=>!v)}>Exit Trade</button>
          <button className="btn btn-ghost btn-sm" style={{color:'var(--red)',borderColor:'#fca5a5'}} onClick={handleDel}>Delete</button>
        </div>
        {exitOpen && (
          <div className="inline-action action-exit">
            <h4>Exit Trade</h4>
            {(t.current_legs||t.legs||[]).map((l,i) => {
              const strike   = l.strike ? `${Number(l.strike).toLocaleString('en-IN')} ` : ''
              const exitSide = l.side === 'BUY' ? 'SELL' : 'BUY'
              return (
                <div key={i} className="form-leg-row form-leg-row-exit">
                  <div className="form-leg-info">
                    <span className={`leg-pill ${exitSide==='BUY'?'leg-pill-buy':'leg-pill-sell'}`}>{exitSide}</span>
                    <div>
                      <div className="rec-leg-sym">{strike}{l.instrument_type} · {fmtQty(l.lots,l.lot_size,l.instrument_type)}</div>
                      <div className="rec-leg-contract">entry {fmtRs(l.price,2)}</div>
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
    const strike     = entry.strike ? `${Number(entry.strike).toLocaleString('en-IN')} ` : ''
    const instrument = entry.instrument_type === 'EQ' ? t.symbol : `${strike}${entry.instrument_type}`
    const legPnl = (entry.price != null && exitLeg?.price != null)
      ? (() => { const qty=(entry.lots||0)*(entry.lot_size||1); return entry.side==='SELL'?(entry.price-exitLeg.price)*qty:(exitLeg.price-entry.price)*qty })()
      : null
    return (
      <tr key={`${entry.id}`} style={bg?{background:bg}:{}}>
        <td><span className={`leg-pill ${entry.side==='BUY'?'leg-pill-buy':'leg-pill-sell'}`}>{entry.side}</span></td>
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
    <div className="trade-card trade-card-closed">
      <div style={{padding:'9px 14px',background:'#f8fafc',display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
        <span style={{fontWeight:700,fontSize:14}}>{t.symbol}</span>
        <span className="badge badge-exited">Closed</span>
        <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,background:'#f1f5f9',color:'var(--muted)',border:'1px solid var(--border)'}}>{t.account_label}</span>
        <span style={{fontSize:11,color:'var(--muted)',marginLeft:'auto',display:'flex',flexDirection:'column',alignItems:'flex-end',gap:1}}>
          <span>In: {t.entry_ist}</span><span>Out: {t.exit_ist}</span>
        </span>
      </div>
      <div className="legs-table-wrap">
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
      </div>
      <div className="pnl-bar">
        <span className="pnl-bar-lbl">Realized P&amp;L</span>
        <span className={pnlCls} style={{fontWeight:700}}>{fmtPnl(pnl)}</span>
      </div>
    </div>
  )
}

// ─── Positions / history panel (right column) ────────────────────────────────

function AccountSummaryBar({ accountId }) {
  const { data } = useAccountPortfolio(accountId)
  const pf = data?.portfolio
  if (!pf || pf.capital == null) return null
  const pnl        = pf.pnl ?? 0
  const upnl       = pf.unrealized_pnl ?? 0
  const usedCap    = pf.used_capital ?? 0
  const pnlColor   = pnl >= 0 ? 'var(--green)' : 'var(--red)'
  const upColor    = upnl >= 0 ? 'var(--green)' : 'var(--red)'
  return (
    <div className="acct-summary-bar">
      <div className="acct-summary-stat">
        <div className="acct-summary-val">{fmtRs(pf.capital)}</div>
        <div className="acct-summary-lbl">Capital</div>
      </div>
      {usedCap > 0 && <>
        <div className="acct-summary-sep" />
        <div className="acct-summary-stat">
          <div className="acct-summary-val" style={{color:'#f59e0b'}}>{fmtRs(usedCap)}</div>
          <div className="acct-summary-lbl">Used (Margin)</div>
        </div>
      </>}
      <div className="acct-summary-sep" />
      <div className="acct-summary-stat">
        <div className="acct-summary-val" style={{color:upColor}}>{upnl >= 0 ? '+' : ''}{fmtRs(upnl)}</div>
        <div className="acct-summary-lbl">Unrealized</div>
      </div>
      <div className="acct-summary-sep" />
      <div className="acct-summary-stat">
        <div className="acct-summary-val" style={{color:pnlColor,fontWeight:700}}>{pnl >= 0 ? '+' : ''}{fmtRs(pnl)}</div>
        <div className="acct-summary-lbl">Total P&amp;L</div>
      </div>
    </div>
  )
}

function NewTradeForm({ accounts, gameAccounts, onDone, openDrawer }) {
  const [acctId, setAcctId] = useState('')
  const [legs, setLegs]     = useState([newLeg()])
  const [note, setNote]     = useState('')
  const push  = useCreateAccountTrade()
  const toast = useToast()

  async function submit() {
    if (!acctId) return toast('Select an account', 'err')
    const collected = collectLegs(legs, toast)
    if (!collected) return
    const res = await push.mutateAsync({ account_id: parseInt(acctId), symbol: collected.symbol, legs: collected.legs, note })
    if (res.ok) { toast('Trade added!', 'ok'); onDone(parseInt(acctId)) }
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="new-trade-ticket anim-pop">
      <div className="form-row">
        <label>Account</label>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <select value={acctId} onChange={e => setAcctId(e.target.value)}>
            <option value="">Select account…</option>
            {accounts.length > 0 && (
              <optgroup label="Broker Accounts">
                {accounts.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.label || [a.broker, a.account_no].filter(Boolean).join(' · ') || `Account ${a.id}`}
                  </option>
                ))}
              </optgroup>
            )}
            {(gameAccounts||[]).length > 0 && (
              <optgroup label="Game Accounts">
                {(gameAccounts||[]).map(a => <option key={a.id} value={a.id}>{a.label || `Game #${a.game_id}`}</option>)}
              </optgroup>
            )}
          </select>
          {openDrawer && <button type="button" className="add-account-link" onClick={() => openDrawer('accounts')}>+ Add</button>}
        </div>
      </div>
      <div className="new-trade-divider" />
      <LegBuilder legs={legs} onChange={setLegs} />
      <div className="form-row" style={{marginTop:4}}>
        <label>Note <span style={{fontWeight:400,textTransform:'none',letterSpacing:0,color:'#94a3b8'}}>(optional)</span></label>
        <input placeholder="e.g. breakout entry, stoploss 24500…" value={note} onChange={e => setNote(e.target.value)} />
      </div>
      <div className="new-trade-footer">
        <button className="btn btn-success" style={{flex:1,justifyContent:'center',fontWeight:600}}
          onClick={submit} disabled={push.isPending}>
          {push.isPending ? 'Adding…' : 'Add Trade'}
        </button>
        <button className="btn btn-ghost" onClick={onDone} style={{color:'var(--muted)'}}>Cancel</button>
      </div>
    </div>
  )
}

function TradesPanel({ isAdmin, openDrawer, switchToAcct, onSwitchDone }) {
  const [posTab, setPosTab]         = useState('open')
  const { data: accounts = [] }     = useAccounts()

  const realAccounts = accounts.filter(a => !a.game_id)
  const gameAccounts = accounts.filter(a => a.game_id && a.game_status === 'active')

  const [acctFilter, setAcctFilter] = useState(() => localStorage.getItem('ev_acct') || '')
  function setAcct(id) {
    setAcctFilter(id)
    if (id) localStorage.setItem('ev_acct', id)
    else localStorage.removeItem('ev_acct')
  }

  useEffect(() => {
    if (!accounts.length) return  // wait for accounts to load before validating
    const allValid = [...realAccounts, ...gameAccounts].map(a => String(a.id))
    if (!acctFilter || !allValid.includes(acctFilter)) {
      setAcct(realAccounts.length ? String(realAccounts[0].id) : '')
    }
  }, [accounts])  // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-switch to newly-pushed account (e.g. game account after push)
  useEffect(() => {
    if (!switchToAcct) return
    const allIds = [...realAccounts, ...gameAccounts].map(a => a.id)
    if (allIds.includes(switchToAcct)) {
      setAcct(String(switchToAcct))
      setPosTab('open')
    }
    onSwitchDone?.()
  }, [switchToAcct])  // eslint-disable-line react-hooks/exhaustive-deps

  const params   = acctFilter ? { account_id: acctFilter } : undefined
  const { data: trades = [], isLoading, refetch }  = useTrades(params)
  const { data: history = [], isLoading: histLoad, refetch: refetchHist } = useTradeHistory(params, posTab === 'history')

  const instrKeys = [...new Set(trades.flatMap(t => {
    const allLegs = [...(t.legs || []), ...(t.applied_adjustments || []).flatMap(a => a.legs || [])]
    return allLegs.map(l => l.instrument_key).filter(Boolean)
  }))]
  const { data: prices = {} } = useRecPrices(instrKeys)

  const title = isAdmin ? 'All Positions' : 'My Positions'

  function acctLabel(a) {
    const base = a.label || [a.broker, a.account_no].filter(Boolean).join(' · ') || `Account ${a.id}`
    return a.user_name ? `${a.user_name} · ${base}` : base
  }

  return (
    <div>
      <div className="card">
        <div className="card-header" style={{gap:0}}>
          <div style={{display:'flex',gap:2}}>
            <button className={`pos-tab${posTab==='open'?' active':''}`} onClick={()=>setPosTab('open')}>{title}</button>
            <button className={`pos-tab${posTab==='history'?' active':''}`} onClick={()=>setPosTab('history')}>History</button>
            {!isAdmin && (
              <button className={`pos-tab pos-tab-new${posTab==='new'?' active':''}`} onClick={()=>setPosTab('new')}>+ New Trade</button>
            )}
          </div>

          {posTab !== 'new' && (
            <div className="trades-header-right">
              {(realAccounts.length > 0 || gameAccounts.length > 0) ? (
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <select value={acctFilter} onChange={e=>setAcct(e.target.value)}
                          style={{width:'auto',fontSize:12,padding:'4px 8px'}}>
                    {realAccounts.length > 0 && (
                      <optgroup label="Broker Accounts">
                        {realAccounts.map(a => <option key={a.id} value={a.id}>{acctLabel(a)}</option>)}
                      </optgroup>
                    )}
                    {gameAccounts.length > 0 && (
                      <optgroup label="Game Accounts">
                        {gameAccounts.map(a => <option key={a.id} value={a.id}>{a.label || `Game #${a.game_id}`}</option>)}
                      </optgroup>
                    )}
                  </select>
                  {!isAdmin && openDrawer && <button type="button" className="add-account-link" onClick={() => openDrawer('accounts')}>+ Add</button>}
                </div>
              ) : (
                !isAdmin && openDrawer &&
                  <button type="button" className="add-account-link" onClick={() => openDrawer('accounts')}>+ Add account</button>
              )}
              <div className="trades-header-divider" />
              <button className="btn btn-ghost btn-sm" onClick={()=>posTab==='open'?refetch():refetchHist()}>↻</button>
            </div>
          )}
        </div>
        <div className="card-body" style={{padding:10}}>
          {posTab !== 'new' && acctFilter && <AccountSummaryBar accountId={parseInt(acctFilter)} />}
          {posTab === 'new' && (
            <NewTradeForm accounts={realAccounts} gameAccounts={gameAccounts} onDone={id => { if (id) setAcct(String(id)); setPosTab('open'); refetch() }} openDrawer={openDrawer} />
          )}
          {posTab === 'open' && (
            isLoading ? <div className="empty">Loading…</div> :
            !trades.length ? <div className="empty">No open positions.</div> :
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

function NoSubscriptionGate() {
  const navigate = useNavigate()
  const toast = useToast()
  const qc    = useQueryClient()
  const { data: credits } = useQuery({ queryKey: ['credits'], queryFn: getCredits, refetchInterval: 15000 })
  const { data: plans = [] } = useQuery({ queryKey: ['plans'], queryFn: getPlans })

  const buy = useMutation({
    mutationFn: subscribeWithCredits,
    onSuccess: res => {
      if (res.ok) {
        toast('Subscription activated! 🎉', 'ok')
        qc.invalidateQueries({ queryKey: ['credits'] })
        setTimeout(() => window.location.reload(), 800)
      } else {
        toast(res.error || 'Failed', 'err')
      }
    },
    onError: () => toast('Something went wrong', 'err'),
  })

  const balance = credits?.balance ?? 0
  const cheapest = plans.length ? Math.min(...plans.map(p => p.gem_cost ?? 0).filter(c => c > 0)) : null
  const canUnlock = cheapest != null && balance >= cheapest

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2>Recommended Positions</h2>
          <span style={{marginLeft:'auto',fontSize:11,fontWeight:600,color:'#94a3b8',display:'flex',alignItems:'center',gap:4}}>
            🔒 Subscription required
          </span>
        </div>
        <div className="card-body" style={{padding:'20px 16px'}}>

        {/* Header */}
        <div style={{textAlign:'center',marginBottom:20}}>
          <div style={{fontSize:36,marginBottom:10}}>🔒</div>
          <div style={{fontSize:15,fontWeight:700,color:'#0f172a',marginBottom:6}}>Unlock live signals</div>
          <div style={{fontSize:13,color:'var(--muted)',lineHeight:1.6}}>
            Play games to earn 💎 gems, then redeem them below to unlock recommendations.
          </div>
        </div>

        {/* Gem balance + how to earn */}
        <div style={{background:'#fefce8',border:'1px solid #fde68a',borderRadius:10,padding:'14px 18px',marginBottom:16}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:8}}>
            <span style={{fontSize:13,color:'#92400e',fontWeight:600}}>Your gem balance</span>
            <span style={{fontSize:20,fontWeight:800,color:'#d97706'}}>💎 {balance}</span>
          </div>
          <div style={{fontSize:11,color:'#b45309',lineHeight:1.5}}>
            Earn gems by playing games — price predictions, quizzes, and trading challenges. Winners get 💎 gems from the reward pool.
          </div>
        </div>

        {/* Plans */}
        {plans.map(plan => {
          const gemCost  = plan.gem_cost ?? 0
          const isFree   = gemCost === 0
          const afford   = isFree || balance >= gemCost
          const need     = gemCost - balance
          const active   = afford && !buy.isPending
          return (
            <div key={plan.id} style={{
              border:`1.5px solid ${afford ? '#6366f1' : 'var(--border)'}`,
              borderRadius:10, padding:'14px 16px', marginBottom:10,
              background: afford ? '#f5f3ff' : '#fff',
              display:'flex', alignItems:'center', justifyContent:'space-between', gap:12,
            }}>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontWeight:700,fontSize:14,color:'#1e293b'}}>{plan.name}</div>
                <div style={{fontSize:12,color:'var(--muted)',marginTop:2}}>{plan.duration_days} days · {plan.description}</div>
                <div style={{fontSize:12,fontWeight:700,color: afford ? '#6366f1' : '#94a3b8',marginTop:4}}>
                  {isFree ? 'Free' : `💎 ${gemCost} gems`}
                </div>
                {!afford && need > 0 && (
                  <div style={{fontSize:11,color:'#f59e0b',marginTop:3,fontWeight:600}}>
                    {need} more gems needed — go play games!
                  </div>
                )}
              </div>
              <button
                disabled={!active}
                onClick={() => buy.mutate(plan.id)}
                style={{
                  flexShrink:0, padding:'8px 16px', borderRadius:7, border:'none',
                  background: active ? '#6366f1' : '#e2e8f0',
                  color: active ? '#fff' : '#94a3b8',
                  fontWeight:700, fontSize:13,
                  cursor: active ? 'pointer' : 'not-allowed', whiteSpace:'nowrap',
                }}
              >
                {isFree ? 'Claim Free' : afford ? `Redeem 💎 ${gemCost}` : `💎 ${gemCost}`}
              </button>
            </div>
          )
        })}

        {/* CTA to Games */}
        <button
          className="btn btn-ghost"
          style={{width:'100%',justifyContent:'center',marginTop:8,fontSize:13}}
          onClick={() => navigate('/games')}
        >
          {canUnlock ? 'Play more games →' : '🎮 Go earn gems in Games →'}
        </button>

        </div>
      </div>
    </div>
  )
}

const TYPE_ICON   = { price_prediction:'🔮', mcq:'📝', leaderboard:'📈' }
const TYPE_LABEL  = { price_prediction:'Prediction', mcq:'Quiz', leaderboard:'Trading Challenge' }
const TYPE_COLOR  = { price_prediction:'#6366f1', mcq:'#8b5cf6', leaderboard:'#22c55e' }

function fmtIstShort(ts) {
  if (!ts) return ''
  const d = new Date(ts.replace('Z','') + (ts.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString('en-IN', { timeZone:'Asia/Kolkata', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', hour12:true })
}

function GamePortfolioStrip({ gid }) {
  const { data } = useQuery({ queryKey: ['portfolio', gid], queryFn: () => getPortfolio(gid), refetchInterval: 10000 })
  const pf = data?.portfolio
  if (!pf) return null

  const unrealized = pf.unrealized_pnl ?? 0
  const total      = pf.pnl ?? 0
  const positions  = (pf.positions || []).length
  const pnlColor   = total >= 0 ? '#16a34a' : '#dc2626'

  return (
    <div className="gsc-portfolio-wrap">
      {pf.label && (
        <div className="gsc-pf-acct-name">{pf.label}</div>
      )}
    <div className="gsc-portfolio">
      <div className="gsc-pf-stat">
        <div className="gsc-pf-lbl">Capital</div>
        <div className="gsc-pf-val">₹{Number(pf.capital||0).toLocaleString('en-IN')}</div>
      </div>
      <div className="gsc-pf-sep" />
      <div className="gsc-pf-stat">
        <div className="gsc-pf-lbl">Unrealised</div>
        <div className="gsc-pf-val" style={{color: unrealized >= 0 ? '#16a34a' : '#dc2626'}}>
          {unrealized >= 0 ? '+' : ''}{fmtRs(unrealized)}
        </div>
      </div>
      <div className="gsc-pf-sep" />
      <div className="gsc-pf-stat">
        <div className="gsc-pf-lbl">Total P&amp;L</div>
        <div className="gsc-pf-val" style={{color: pnlColor, fontWeight:700}}>
          {total >= 0 ? '+' : ''}{fmtRs(total)}
        </div>
      </div>
      <div className="gsc-pf-sep" />
      <div className="gsc-pf-stat">
        <div className="gsc-pf-lbl">Positions</div>
        <div className="gsc-pf-val">{positions}</div>
      </div>
    </div>
    </div>
  )
}

function GameStripCard({ g }) {
  const navigate = useNavigate()
  const qc    = useQueryClient()
  const toast = useToast()
  const [joining, setJoining] = useState(false)

  const isLive  = g.status === 'active'
  const joined  = !!g.my_entry
  const canJoin = isLive && !joined && g.game_type === 'leaderboard'
  const canPlay = isLive && !joined && g.game_type !== 'leaderboard'
  const accent  = TYPE_COLOR[g.game_type] || '#6366f1'

  async function handleJoin(e) {
    e.stopPropagation()
    setJoining(true)
    try {
      const res = await submitEntry(g.id, {})
      if (res.ok) { toast('Joined! Virtual account ready.', 'ok'); qc.invalidateQueries({queryKey:['games']}) }
      else toast(res.error || 'Failed to join', 'err')
    } finally { setJoining(false) }
  }

  return (
    <div className="gsc" style={{'--gsc-accent': accent}} onClick={() => navigate(`/games/${g.id}`)}>
      {/* Header row */}
      <div className="gsc-header">
        <span className="gsc-icon">{TYPE_ICON[g.game_type]}</span>
        <span className="gsc-type">{TYPE_LABEL[g.game_type]}</span>
        <span className={`gsc-status ${isLive ? 'gsc-live' : 'gsc-soon'}`}>{isLive ? '● Live' : '◌ Soon'}</span>
        <span className="gsc-pool">💎 {g.reward_pool}</span>
      </div>

      {/* Title */}
      <div className="gsc-title">{g.title}</div>

      {/* Meta */}
      <div className="gsc-meta">
        <span>{isLive ? `Ends ${fmtIstShort(g.end_time)}` : `Starts ${fmtIstShort(g.start_time)}`}</span>
        <span className="gsc-dot">·</span>
        <span>👥 {g.participant_count}</span>
        <span className="gsc-dot">·</span>
        <span>🏆 Top {g.winner_count}</span>
      </div>

      {/* Portfolio strip for joined leaderboard */}
      {joined && g.game_type === 'leaderboard' && isLive && (
        <GamePortfolioStrip gid={g.id} />
      )}

      {/* Divider + actions */}
      <div className="gsc-footer" onClick={e => e.stopPropagation()}>
        <div className="gsc-entry-status">
          {joined && (
            <span className="gsc-joined">
              ✓ Joined{g.my_entry?.rank > 0 ? <strong> · Rank #{g.my_entry.rank}</strong> : ''}
            </span>
          )}
          {joined && g.my_entry?.credits_won > 0 && (
            <span className="gsc-won">💎 {g.my_entry.credits_won} won</span>
          )}
        </div>
        <div className="gsc-actions">
          {canJoin && (
            <button className="gsc-btn gsc-btn-primary" onClick={handleJoin} disabled={joining}>
              {joining ? 'Joining…' : 'Join →'}
            </button>
          )}
          {canPlay && (
            <button className="gsc-btn gsc-btn-primary" onClick={() => navigate(`/games/${g.id}`)}>
              Play →
            </button>
          )}
          <button className="gsc-btn gsc-btn-ghost" onClick={() => navigate(`/games/${g.id}`)}>
            View
          </button>
        </div>
      </div>
    </div>
  )
}

function GamesStrip() {
  const navigate = useNavigate()
  const { data: games = [] } = useQuery({ queryKey: ['games'], queryFn: listGames, refetchInterval: 60000 })

  const liveGames     = games.filter(g => g.status === 'active')
  const upcomingGames = games.filter(g => g.status === 'draft' && g.start_time && new Date(g.start_time) > new Date())
  const shown = [...liveGames, ...upcomingGames].slice(0, 5)

  if (!shown.length) return null

  return (
    <div className="card" style={{marginTop:12}}>
      <div className="card-header">
        <span style={{fontWeight:700,fontSize:13}}>🎮 Games</span>
        <button className="btn btn-ghost btn-sm" style={{marginLeft:'auto'}} onClick={() => navigate('/games')}>All →</button>
      </div>
      <div style={{padding:'6px 10px 12px',display:'flex',flexDirection:'column',gap:8}}>
        {shown.map(g => <GameStripCard key={g.id} g={g} />)}
      </div>
    </div>
  )
}

export default function Dashboard({ openDrawer, subscribed }) {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const [switchToAcct, setSwitchToAcct] = useState(null)

  return (
    <div className="dash-layout">
      {isAdmin || subscribed
        ? <RecsPanel isAdmin={isAdmin} openDrawer={openDrawer} onPushed={id => setSwitchToAcct(id)} />
        : <NoSubscriptionGate />}
      <div>
        <TradesPanel isAdmin={isAdmin} openDrawer={openDrawer} switchToAcct={switchToAcct} onSwitchDone={() => setSwitchToAcct(null)} />
        <GamesStrip />
      </div>
    </div>
  )
}
