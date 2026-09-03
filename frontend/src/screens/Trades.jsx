import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useRecs, useRecPrices, useCreateRec, useDeleteRec, useExitRec, useAdjustRec, useCreateAccountTrade,
         useAccounts } from '../hooks/useTrades'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCredits, getPlans, subscribeWithCredits } from '../api/games'
import { loadRazorpayScript } from '../api/billing'
import { useCreateOrder, useVerifyPayment } from '../hooks/useBilling'
import useAuthStore from '../store/authStore'
import { useToast } from '../components/common/Toast'
import LegBuilder from '../components/trades/LegBuilder'
import Dropdown from '../components/common/Dropdown'
import { newLeg, collectLegs } from '../components/trades/legHelpers'
import LegGroup from '../components/trades/LegDisplay'
import { fmtRs, fmtPnl, fmtQty, fmtContract } from '../utils/format'
import { unrealizedPnl, realizedPnl } from '../utils/pnl'
import { BankIcon, GameIcon, GemIcon, LockIcon, RefreshIcon, CardIcon } from '../components/common/Icons'
import MonthSummaryCard from './profile/MonthSummaryCard'
import { currentIstMonth, monthLabel, istMonthFromDisplay } from './profile/reportUtils'
import './Trades.css'

// ─── Risk level ────────────────────────────────────────────────────────────
// Qualitative, admin-assigned at creation time — no query can compute it
// after the fact, so trades created before this field existed just stay
// unset (shown as — / filtered under "Unset") rather than being backfilled.

const RISK_LEVELS = [
  { value: 'low',       label: 'Low' },
  { value: 'mid',       label: 'Mid' },
  { value: 'high',      label: 'High' },
  { value: 'very_high', label: 'Very High' },
]
const RISK_LABEL = Object.fromEntries(RISK_LEVELS.map(r => [r.value, r.label]))

// ─── Create recommendation form (admin) ──────────────────────────────────────

function CreateRecForm() {
  const [legs, setLegs]           = useState([newLeg()])
  const [note, setNote]           = useState('')
  const [riskLevel, setRiskLevel] = useState('')
  const create = useCreateRec()
  const toast  = useToast()

  async function submit() {
    if (!note.trim()) { toast('Title is required', 'err'); return }
    if (!riskLevel) { toast('Risk level is required', 'err'); return }
    const data = collectLegs(legs, toast)
    if (!data) return
    const res = await create.mutateAsync({ ...data, note, risk_level: riskLevel })
    if (res.ok) {
      toast(`Recommendation created (id=${res.trade_id}) ✓`, 'ok')
      setLegs([newLeg()]); setNote(''); setRiskLevel('')
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
        <div className="form-row" style={{marginBottom:12}}>
          <label>Risk Level <span style={{color:'var(--red)'}}>*</span></label>
          <Dropdown variant="form" value={riskLevel} onChange={setRiskLevel}
            placeholder="Select risk level…" options={RISK_LEVELS} />
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

// fmtContract, OpenLeg, ExitedLeg, LegGroup live in components/trades/LegDisplay.jsx
// — shared with Positions.jsx's TradeCard/HistoryCard, which render the same
// kind of data (a position's legs).

function RecLegs({ rec, prices }) {
  const exitLegs = rec.status === 'exited' ? rec.exit_legs : null
  const adjs     = rec.adjustments || []

  return (
    <div className="rec-legs">
      <LegGroup type="entry" title="Entry"
        legs={rec.legs} symbol={rec.symbol} exitLegs={exitLegs} prices={prices} />

      {adjs.map((a, ai) => (
        <div key={a.id || ai}>
          <div className="adj-connector">↓ Adjustment {ai + 1}{a.ts_ist ? ` · ${a.ts_ist}` : ''}</div>
          <LegGroup type="adj" note={a.note}
            legs={a.legs || []} symbol={rec.symbol} exitLegs={exitLegs} prices={prices} />
        </div>
      ))}

    </div>
  )
}

// ─── Push to account form (client) ───────────────────────────────────────────

function PushForm({ rec, prices, onClose, onPushed }) {
  const navigate = useNavigate()
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
          <Dropdown variant="form" value={acctId} onChange={setAcctId} placeholder="Select account…"
            groups={[
              { label: 'Broker Accounts', options: realAccounts.map(a => ({
                  value: String(a.id), label: a.label || [a.broker, a.account_no].filter(Boolean).join(' · ') || `Account ${a.id}` })) },
              { label: 'Game Accounts', options: gameAccounts.map(a => ({
                  value: String(a.id), label: a.label || `Game #${a.game_id}` })) },
            ]} />
          <button type="button" className="add-account-link" onClick={() => navigate('/profile/accounts')}>+ Add</button>
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

function RecItem({ rec, prices, onPushed, highlight }) {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const toast   = useToast()

  const [collapsed, setCollapsed] = useState(!highlight)
  const [adjOpen,  setAdjOpen]  = useState(false)
  const [exitOpen, setExitOpen] = useState(false)
  const [pushOpen, setPushOpen] = useState(false)
  const doDel  = useDeleteRec()
  const isOpen = rec.status === 'open'

  // Realized/unrealized P&L — shared with Dashboard.jsx's monthly summary,
  // see utils/pnl.js for why instrument_key matching (not positional zip()).
  const totalPnl      = realizedPnl(rec)
  const unrealisedPnl = unrealizedPnl(rec, prices)

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
            {rec.segment && <span className="rec-seg-tag">{rec.segment}</span>}
            {rec.risk_level && <span className={`risk-badge risk-${rec.risk_level}`}>{RISK_LABEL[rec.risk_level] || rec.risk_level}</span>}
            <span className={`status-dot status-dot-${rec.status === 'open' ? 'open' : 'exited'}`}
                  title={rec.status === 'open' ? 'Live' : 'Exited'} />
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
        <div className="rec-ts">
          {rec.entry_ist}{rec.exit_ist ? ` → ${rec.exit_ist}` : ''}
        </div>
        <div className="rec-adj-strip">
          <span className="rec-code">#{rec.display_code || rec.id}</span>
          {rec.adj_count > 0 && <span className="rec-adj-text"> · {rec.adj_count} adjustment{rec.adj_count > 1 ? 's' : ''}</span>}
        </div>
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
              {pushOpen && <PushForm rec={rec} prices={prices} onClose={() => setPushOpen(false)} onPushed={onPushed} />}
            </>
      )}

      </div>
    </div>
  )
}

// ─── Recommendations panel (left column) ─────────────────────────────────────

const SEGMENTS = ['all', 'F&O', 'Equity', 'ETF', 'Commodities']

function RecsPanel({ isAdmin, subscribed }) {
  const canSeeList = isAdmin || subscribed
  const navigate = useNavigate()
  const [status,  setStatus]  = useState('open')
  const [segment, setSegment] = useState('all')
  const [risk,    setRisk]    = useState('all')
  // Which month the Exited list itself is scoped to — driven by
  // MonthSummaryCard's own Booked-tile month-nav (only visible/relevant
  // when status === 'exited', see the compact card below) so the position
  // list and the summary numbers above it always agree on what "this
  // month" means, instead of the summary showing e.g. July while the list
  // still shows every exited trade ever.
  const [bookedMonth, setBookedMonth] = useState(() => currentIstMonth())
  const { data: allRecs = [], isLoading, refetch } = useRecs()
  const { data: accounts = [] } = useAccounts()
  const [searchParams, setSearchParams] = useSearchParams()
  const highlightId = searchParams.get('rec') ? parseInt(searchParams.get('rec')) : null

  // Deep-link support for `?status=open|exited` — e.g. an old bookmark/link
  // into a filtered view. Reacts to searchParams changing (not just once at
  // mount) since navigating here from elsewhere on Trades itself changes the
  // URL without remounting this component. Self-clears the param immediately
  // after applying (same pattern as `?rec=` below) so it acts like a
  // one-time instruction, never a param this screen keeps in sync with — a
  // later toggle click is free to diverge from the URL without this effect
  // stomping back over it.
  useEffect(() => {
    const s = searchParams.get('status')
    if (s !== 'open' && s !== 'exited') return
    setStatus(s)
    setSearchParams(p => { p.delete('status'); return p }, { replace: true })
  }, [searchParams])  // eslint-disable-line react-hooks/exhaustive-deps

  // When recs load and ?rec= is set, switch filter to show it then scroll to it
  useEffect(() => {
    if (!highlightId || !allRecs.length) return
    const target = allRecs.find(r => r.id === highlightId)
    if (!target) return
    // Make sure the right status filter is active — only Open/Exited exist
    // now, so an exited target always means switching to Exited, not a
    // former "all" catch-all. For an exited target, also point bookedMonth
    // at whichever month it actually exited in — the Exited list is now
    // scoped to bookedMonth (see that state's own comment), so without this
    // a target that exited in an earlier month would get the right status
    // but still not appear in `filtered`, and the scroll-to below would
    // silently find nothing.
    if (target.status === 'open' && status !== 'open') setStatus('open')
    if (target.status !== 'open') {
      if (status !== 'exited') setStatus('exited')
      const exitMonth = istMonthFromDisplay(target.exit_ist)
      if (exitMonth && exitMonth !== bookedMonth) setBookedMonth(exitMonth)
    }
    // Scroll after a tick so the DOM has rendered
    setTimeout(() => {
      document.getElementById(`rec-${highlightId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 100)
    // Clear the param after 3s so it doesn't linger
    const t = setTimeout(() => setSearchParams(p => { p.delete('rec'); return p }), 3000)
    return () => clearTimeout(t)
  }, [highlightId, allRecs.length])  // eslint-disable-line react-hooks/exhaustive-deps

  // Client-side status filter (Flask returns all recs; ignores ?status= param).
  // Exited is additionally scoped to bookedMonth — see the field's own
  // comment above for why the list needs to track the summary card's month.
  const recs = status === 'exited'
    ? allRecs.filter(r => r.status !== 'open' && istMonthFromDisplay(r.exit_ist) === bookedMonth)
    : allRecs.filter(r => r.status === 'open')

  const usedSegs = new Set(allRecs.map(r => r.segment))
  const bySegment = segment === 'all' ? recs : recs.filter(r => r.segment === segment)
  const filtered  = risk === 'all' ? bySegment : bySegment.filter(r => r.risk_level === risk)

  // Poll live LTPs for open rec legs
  const instrKeys = [...new Set(
    allRecs.filter(r => r.status === 'open')
           .flatMap(r => (r.current_legs || r.legs || []).map(l => l.instrument_key).filter(Boolean))
  )]
  const { data: prices = {} } = useRecPrices(instrKeys)

  // A trade was just pushed to one of the user's accounts — Positions is now
  // its own route rather than a sibling panel, so hop over there to show it.
  // Carry the account id along (?account=) so Positions selects that account
  // instead of defaulting to the first one — restores the auto-switch this
  // page used to do in-place before the split (see Positions.jsx's read of
  // this param).
  function handlePushed(acctId) { navigate(acctId ? `/positions?account=${acctId}` : '/positions') }

  return (
    <div>
      {isAdmin && <CreateRecForm />}

      {/* Client setup banner — only once they can actually push a trade to
          an account, i.e. once subscribed; showing this to an unsubscribed
          client would push them toward account setup before they even have
          anything to push. */}
      {!isAdmin && subscribed && accounts.length === 0 && (
        <div className="card">
          <div className="card-body" style={{textAlign:'center',padding:'28px 20px'}}>
            <div style={{color:'var(--muted)',display:'flex',justifyContent:'center',marginBottom:10}}><BankIcon size={30}/></div>
            <div style={{fontSize:14,fontWeight:700,marginBottom:6}}>Set up your accounts</div>
            <div style={{fontSize:13,color:'var(--muted)',marginBottom:18}}>Add your brokerage accounts to start pushing trades from recommendations.</div>
            <button className="btn btn-primary" onClick={() => navigate('/profile/accounts')}>Open Account Settings →</button>
          </div>
        </div>
      )}

      {/* Compact summary card — this IS the status filter now (the Open/
          Exited toggle at its top), not just a display that mirrors one
          kept elsewhere: the position list below reads the very state this
          card controls, so the two can never disagree on which status is
          active. This is the one thing that stays visible without a
          subscription — everything position-specific (segment/risk filters,
          the list itself) is bundled into the gate below instead. */}
      <MonthSummaryCard compact status={status} onStatusChange={setStatus}
                        month={bookedMonth} onMonthChange={setBookedMonth} />

      {!canSeeList && <UnlockPanel />}

      {canSeeList && (
        <div className="card">
          <div className="card-header">
            <h2>{status === 'open' ? 'Open Positions' : 'Exited Positions'}</h2>
            <button className="btn btn-ghost btn-sm" style={{marginLeft:'auto',display:'inline-flex'}} onClick={refetch}><RefreshIcon/></button>
          </div>

          <div style={{display:'flex',alignItems:'center',gap:6,flexWrap:'wrap',padding:'8px 16px 6px',borderBottom:'1px solid var(--border)',background:'#fafafa'}}>
            <Dropdown value={segment} onChange={setSegment}
              options={SEGMENTS.filter(s => s === 'all' || usedSegs.has(s)).map(s => ({value:s, label: s === 'all' ? 'All Segments' : s}))} />
            <div style={{marginLeft:'auto',display:'flex',alignItems:'center',gap:8}}>
              <Dropdown value={risk} onChange={setRisk} align="right"
                options={[
                  {value:'all', label:'All Risk'},
                  ...RISK_LEVELS.map(r => ({
                    value: r.value,
                    label: <><span className={`status-dot status-dot-risk-${r.value}`} style={{marginRight:6}}/>{r.label}</>,
                  })),
                ]} />
            </div>
          </div>

          <div className="card-body" style={{padding:10}}>
            {isLoading && <div className="empty">Loading…</div>}
            {!isLoading && !filtered.length && (
              <div className="empty">
                No {segment !== 'all' ? segment + ' ' : ''}{status} recommendations
                {status === 'exited' ? ` in ${monthLabel(bookedMonth)}` : ''}.
              </div>
            )}
            {filtered.map(r => <RecItem key={r.id} rec={r} prices={prices} onPushed={handlePushed} highlight={r.id === highlightId} />)}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Unlock panel — replaces just the recommendation list (not the whole
// screen) when the client has no active subscription; the ROI summary and
// the segment/risk/status filters above it stay live regardless. ─────────

// One plan's two independent unlock paths, laid out so it reads as "pay OR
// redeem" — never both required, never "this card is selected". A plan is
// only ever server-side "free" when price === 0 (docs/apis.md's
// POST /api/subscribe: "Only free plans (price == 0)") — gem_cost === 0
// means "no gem option for this plan", not "free", so those two must never
// be conflated even though today every active plan happens to price both.
function OrDivider() {
  return (
    <div style={{display:'flex',alignItems:'center',gap:10,margin:'2px 0'}}>
      <div style={{flex:1,height:1,background:'#eef0f4'}}/>
      <span style={{fontSize:9.5,fontWeight:800,color:'#cbd5e1',letterSpacing:.6}}>OR</span>
      <div style={{flex:1,height:1,background:'#eef0f4'}}/>
    </div>
  )
}

function PlanUnlockCard({ plan, balance, onRedeem, onPay, redeeming, paying }) {
  const gemCost   = plan.gem_cost ?? 0
  const price     = plan.price ?? 0
  const isFree    = price === 0
  const hasMoney  = !isFree && price > 0
  const hasGems   = !isFree && gemCost > 0
  const afford    = gemCost > 0 && balance >= gemCost
  const need      = gemCost - balance

  return (
    <div className="plan-scroll-card" style={{
      border:'1px solid #e6e9f0', borderRadius:14, background:'#fff',
      boxShadow:'0 1px 2px rgba(15,23,42,.04)', overflow:'hidden',
    }}>
      <div style={{padding:'14px 16px 12px'}}>
        {/* fontSize clamp()s with the viewport so the name shrinks along
            with the card at the narrow end of .plan-scroll-card's own
            clamp() width — without it, the fixed 15px name + the nowrap
            duration pill didn't both fit on one line at the card's minimum
            (210px) width and the name wrapped to a second line. minWidth:0
            + ellipsis is the hard backstop for a plan name long enough that
            even the shrunk font still doesn't fit — truncates instead of
            wrapping or pushing the pill out of the card. */}
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8,marginBottom:4}}>
          <span style={{fontWeight:800,fontSize:'clamp(13px,4.2vw,15px)',color:'#0f172a',minWidth:0,overflow:'hidden',whiteSpace:'nowrap',textOverflow:'ellipsis'}}>{plan.name}</span>
          <span style={{fontSize:'clamp(9.5px,2.6vw,10.5px)',fontWeight:800,color:'#4338ca',background:'#eef2ff',padding:'3px 10px',borderRadius:20,flexShrink:0,whiteSpace:'nowrap'}}>
            {plan.duration_days} DAYS
          </span>
        </div>
        {/* Fixed height (not content-driven) so a plan with no description
            — e.g. the real "Janmashtami Offer" plan, description:'' today —
            reserves the exact same space as one that has it. Without this,
            that card's button row would start higher than its neighbors',
            and in a horizontal scroll row that misalignment is much more
            visible than it was stacked vertically. Single line + ellipsis
            for the same reason in the other direction: an unusually long
            description shouldn't grow one card taller than the rest either. */}
        <div style={{fontSize:12,color:'var(--muted)',lineHeight:1.5,height:18,overflow:'hidden',whiteSpace:'nowrap',textOverflow:'ellipsis'}}>
          {plan.description}
        </div>
      </div>

      <div style={{height:1,background:'#f1f4f8'}}/>

      <div style={{padding:'12px 16px 14px'}}>
        {isFree ? (
          <button className="btn btn-primary" style={{width:'100%',justifyContent:'center',padding:'10px 14px',fontSize:'clamp(11.5px,3.4vw,13.5px)'}}
            disabled={redeeming} onClick={() => onRedeem(plan.id)}>
            Claim Free
          </button>
        ) : (
          <div style={{display:'flex',flexDirection:'column',gap:8}}>
            {/* Button fontSize clamp()s down at narrow card widths, same
                fluid-not-fixed reasoning as the name/badge row above. The
                label (icon+text) span gets minWidth:0 + ellipsis so it's
                the one that truncates if it's still tight after shrinking
                — the price/gem-count on the right is the number the user
                actually needs to see, so it stays flexShrink:0/nowrap and
                is never the thing that gives up space. */}
            {hasMoney && (
              <button disabled={paying} onClick={() => onPay(plan)}
                style={{
                  display:'flex', alignItems:'center', justifyContent:'space-between', width:'100%',
                  padding:'11px 16px', borderRadius:9, border:'1.5px solid #6366f1', background:'#fbfbff',
                  color:'#4f46e5', fontWeight:700, fontSize:'clamp(11.5px,3.4vw,13.5px)', cursor: paying ? 'not-allowed' : 'pointer',
                }}>
                <span style={{display:'flex',alignItems:'center',gap:7,minWidth:0,overflow:'hidden'}}>
                  <CardIcon size={14}/>
                  <span style={{overflow:'hidden',whiteSpace:'nowrap',textOverflow:'ellipsis'}}>Pay with money</span>
                </span>
                <span style={{fontSize:'clamp(13px,3.8vw,15px)',fontWeight:800,flexShrink:0,whiteSpace:'nowrap',marginLeft:8}}>{paying ? 'Opening…' : `₹${price}`}</span>
              </button>
            )}
            {hasMoney && hasGems && <OrDivider />}
            {hasGems && (
              <button disabled={!afford || redeeming} onClick={() => onRedeem(plan.id)}
                style={{
                  display:'flex', alignItems:'center', justifyContent:'space-between', width:'100%',
                  padding:'11px 16px', borderRadius:9, border:'none',
                  background: afford ? 'linear-gradient(135deg,#6366f1,#4f46e5)' : '#eef0f4',
                  color: afford ? '#fff' : '#94a3b8', boxShadow: afford ? '0 2px 6px rgba(79,70,229,.28)' : 'none',
                  fontWeight:700, fontSize:'clamp(11.5px,3.4vw,13.5px)', cursor: afford ? 'pointer' : 'not-allowed',
                }}>
                <span style={{display:'flex',alignItems:'center',gap:7,minWidth:0,overflow:'hidden'}}>
                  <GemIcon size={14}/>
                  <span style={{overflow:'hidden',whiteSpace:'nowrap',textOverflow:'ellipsis'}}>Redeem with gems</span>
                </span>
                <span style={{fontSize:'clamp(13px,3.8vw,15px)',fontWeight:800,flexShrink:0,whiteSpace:'nowrap',marginLeft:8}}>{gemCost}</span>
              </button>
            )}
            {hasGems && !afford && (
              <div style={{textAlign:'center',fontSize:11,fontWeight:700,color:'#b45309',background:'#fffbeb',border:'1px solid #fde68a',borderRadius:20,padding:'3px 10px'}}>
                {need} more gem{need===1?'':'s'} needed
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function UnlockPanel() {
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

  const createOrder   = useCreateOrder()
  const verifyPayment = useVerifyPayment()
  const [payingPlanId, setPayingPlanId] = useState(null)

  async function payWithRazorpay(plan) {
    setPayingPlanId(plan.id)
    try {
      if (!(await loadRazorpayScript())) { toast('Could not load payment gateway', 'err'); return }
      const order = await createOrder.mutateAsync(plan.id)
      if (!order.ok) { toast(order.error || 'Could not start payment', 'err'); return }
      const rzp = new window.Razorpay({
        key: order.key_id, order_id: order.order_id, amount: order.amount, currency: order.currency,
        name: 'EdgeVest', description: plan.name,
        handler: async (resp) => {
          const res = await verifyPayment.mutateAsync({
            razorpay_order_id:   resp.razorpay_order_id,
            razorpay_payment_id: resp.razorpay_payment_id,
            razorpay_signature:  resp.razorpay_signature,
          })
          if (res.ok) { toast('Subscription activated! 🎉', 'ok'); setTimeout(() => window.location.reload(), 800) }
          else toast(res.error || 'Payment verification failed', 'err')
        },
        modal: { ondismiss: () => toast('Payment cancelled', 'err') },
      })
      rzp.on('payment.failed', () => toast('Payment failed', 'err'))
      rzp.open()
    } finally {
      setPayingPlanId(null)
    }
  }

  const balance = credits?.balance ?? 0

  return (
    <div className="card">
      <div className="card-header">
        <h2>Recommended Positions</h2>
        <span style={{marginLeft:'auto',fontSize:11,fontWeight:600,color:'#94a3b8',display:'flex',alignItems:'center',gap:4}}>
          <LockIcon size={12}/> Subscription required
        </span>
      </div>
      <div className="card-body" style={{padding:'18px 16px'}}>

      <div style={{textAlign:'center',marginBottom:16}}>
        <div style={{color:'var(--muted)',display:'flex',justifyContent:'center',marginBottom:8}}><LockIcon size={26}/></div>
        <div style={{fontSize:14,fontWeight:700,color:'#0f172a',marginBottom:4}}>Subscribe to see recommendations</div>
        <div style={{fontSize:12,color:'var(--muted)',lineHeight:1.55,maxWidth:320,margin:'0 auto'}}>
          Pay once, or redeem <GemIcon size={11}/> gems you&apos;ve earned playing games — either one unlocks the same plan.
        </div>
      </div>

      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',background:'#fefce8',border:'1px solid #fde68a',borderRadius:10,padding:'10px 14px',marginBottom:14}}>
        <span style={{fontSize:12,color:'#92400e',fontWeight:600}}>Your gem balance</span>
        <span style={{fontSize:17,fontWeight:800,color:'#d97706',display:'inline-flex',alignItems:'center',gap:5}}><GemIcon size={14}/> {balance}</span>
      </div>

      <div className="plan-scroll">
        {plans.map(plan => (
          <PlanUnlockCard key={plan.id} plan={plan} balance={balance}
            onRedeem={id => buy.mutate(id)} onPay={payWithRazorpay}
            redeeming={buy.isPending} paying={payingPlanId === plan.id} />
        ))}
      </div>
      {plans.length > 1 && (
        <div style={{textAlign:'center',fontSize:10.5,color:'#cbd5e1',fontWeight:600,margin:'-6px 0 12px'}}>
          ‹ swipe for more plans ›
        </div>
      )}

      <button
        className="btn btn-ghost"
        style={{width:'100%',justifyContent:'center',marginTop:4,fontSize:13,display:'flex',alignItems:'center',gap:6}}
        onClick={() => navigate('/games')}
      >
        <GameIcon size={13}/> Earn more gems in Games →
      </button>

      </div>
    </div>
  )
}

export default function Trades({ subscribed }) {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'

  return (
    <div className="trades-layout">
      <RecsPanel isAdmin={isAdmin} subscribed={subscribed} />
    </div>
  )
}
