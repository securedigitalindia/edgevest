import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTrades, useTradeHistory, useExitTrade, useApplyAdjTrade, useDeleteTrade,
         useAccounts, useAccountPortfolio, useCreateAccountTrade, useRecPrices } from '../hooks/useTrades'
import useAuthStore from '../store/authStore'
import { useToast } from '../components/common/Toast'
import PageHeader from '../components/common/PageHeader'
import Dropdown from '../components/common/Dropdown'
import LegBuilder from '../components/trades/LegBuilder'
import { newLeg, collectLegs } from '../components/trades/legHelpers'
import LegGroup from '../components/trades/LegDisplay'
import { BankIcon, GameIcon, ChevronIcon, PlusIcon, TrendIcon, BellIcon, RefreshIcon, CloseIcon } from '../components/common/Icons'
import { fmtRs, fmtPnl, fmtQty } from '../utils/format'
import './Positions.css'

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

  return (
    <div className="trade-card">
      <div className="rec-header">
        <div style={{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
          <span className="rec-symbol">{t.symbol}</span>
          {t.segment && <span className="rec-seg-tag">{t.segment}</span>}
          {t.risk_level && <span className={`risk-badge risk-${t.risk_level}`}>{RISK_LABEL[t.risk_level] || t.risk_level}</span>}
          {t.pending_exit && (
            <span className="badge badge-danger" style={{display:'inline-flex',alignItems:'center',gap:4}}><BellIcon size={10}/> exit pending</span>
          )}
          <span className="status-dot status-dot-open" title="Open" />
        </div>
        <div className="rec-ts">{t.entry_ist}</div>
        {(t.display_code || t.rec_id) && (
          <div className="rec-adj-strip">
            <span className="rec-code">#{t.display_code || t.rec_id}</span>
            {t.pending_adj_count > 0 && <span className="rec-adj-text"> · {t.pending_adj_count} adjustment{t.pending_adj_count > 1 ? 's' : ''} pending</span>}
          </div>
        )}
      </div>

      <div className="rec-legs">
        <LegGroup type="entry" title="Entry" legs={t.legs} symbol={t.symbol} prices={prices} />
        {(t.applied_adjustments||[]).map((a, ai) => (
          <LegGroup key={a.id || ai} type="adj" title={`Adjustment ${ai+1}`} note={a.note}
            legs={a.legs||[]} symbol={t.symbol} prices={prices} />
        ))}
      </div>

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
          <div className="rec-stats-strip">
            {t.margin != null && (
              <div className="rec-stat">
                <div className="rec-stat-lbl">Margin</div>
                <div className="rec-stat-val">₹{Math.round(t.margin).toLocaleString('en-IN')}</div>
              </div>
            )}
            <div className="rec-stat">
              <div className="rec-stat-lbl">Unrealised P&amp;L</div>
              <div className="rec-stat-val" style={{color: allKnown ? (net>=0?'var(--green)':'var(--red)') : 'var(--muted)'}}>
                {allKnown ? fmtPnl(net) : '—'}
              </div>
            </div>
          </div>
        )
      })()}

      {(t.pending_adjustments||[]).length > 0 && <PendingAdjSection trade={t} />}

      {t.pending_exit && (
        <div style={{padding:'10px 14px',borderTop:'2px solid #ef4444',background:'#fff1f2',display:'flex',alignItems:'flex-start',gap:10}}>
          <span style={{color:'#dc2626',flexShrink:0,display:'inline-flex'}}><BellIcon size={18}/></span>
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontWeight:700,fontSize:12,color:'#b91c1c',textTransform:'uppercase',letterSpacing:.4,marginBottom:2}}>
              Recommendation Exited
            </div>
            <div style={{fontSize:12,color:'#7f1d1d'}}>
              The recommendation for this trade has been closed. Please exit your position.
            </div>
          </div>
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

  // Pre-compute exit leg pairings — positional against t.exit_legs, not by
  // instrument_key (account-trade exit legs aren't guaranteed to carry one,
  // unlike recommended-trade exit_legs), so this stays separate from
  // LegGroup's own instrument_key matching and feeds it pre-paired instead.
  const origLen = origLegs.length
  const adjOffsets = adjGroups.map((_, ai) =>
    origLen + adjGroups.slice(0, ai).reduce((s, g2) => s + g2.legs.length, 0)
  )
  const entryPairs = origLegs.map((e, i) => ({ entry: e, exitLeg: t.exit_legs?.[i] }))

  return (
    <div className="trade-card trade-card-closed">
      <div className="rec-header">
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:8,flexWrap:'wrap'}}>
          <div style={{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
            <span className="rec-symbol">{t.symbol}</span>
            {t.segment && <span className="rec-seg-tag">{t.segment}</span>}
            {t.risk_level && <span className={`risk-badge risk-${t.risk_level}`}>{RISK_LABEL[t.risk_level] || t.risk_level}</span>}
            <span className="status-dot status-dot-exited" title="Closed" />
          </div>
          <div className="rec-ts" style={{textAlign:'right'}}>
            {t.entry_ist} → {t.exit_ist}
            {(t.display_code || t.rec_id) && <> · <span className="rec-code">#{t.display_code || t.rec_id}</span></>}
          </div>
        </div>
      </div>

      <div className="rec-legs">
        <LegGroup type="entry" title="Entry" pairs={entryPairs} symbol={t.symbol} />
        {adjGroups.map((g, ai) => {
          const offset = adjOffsets[ai]
          const pairs  = g.legs.map((e, j) => ({ entry: e, exitLeg: t.exit_legs?.[offset + j] }))
          return <LegGroup key={g.adj_id || ai} type="adj" title={`Adjustment ${ai+1}`} pairs={pairs} symbol={t.symbol} />
        })}
      </div>

      <div className="rec-stats-strip">
        <div className="rec-stat">
          <div className="rec-stat-lbl">Realized P&amp;L</div>
          <div className={`rec-stat-val ${pnlCls}`}>{fmtPnl(pnl)}</div>
        </div>
      </div>
    </div>
  )
}

// ─── Capital / P&L summary — hero Total P&L + used-capital proportion bar ────

function CapitalSummary({ accountId }) {
  const { data } = useAccountPortfolio(accountId)
  const pf = data?.portfolio
  if (!pf || pf.capital == null) return null
  const pnl      = pf.pnl ?? 0
  const upnl     = pf.unrealized_pnl ?? 0
  const usedCap  = pf.used_capital ?? 0
  const capital  = pf.capital ?? 0
  const pnlColor = pnl >= 0 ? 'var(--green)' : 'var(--red)'
  const upColor  = upnl >= 0 ? 'var(--green)' : 'var(--red)'
  const pct      = capital > 0 ? Math.min(100, (usedCap / capital) * 100) : 0

  return (
    <div className="card cap-summary">
      <div className="cap-summary-hero">
        <div>
          <div className="cap-summary-lbl">Total P&amp;L</div>
          <div className="cap-summary-pnl-row">
            <span className="cap-summary-pnl" style={{color:pnlColor}}>{pnl >= 0 ? '+' : ''}{fmtRs(pnl)}</span>
            <span style={{color:pnlColor,display:'inline-flex'}}><TrendIcon up={pnl >= 0} /></span>
          </div>
        </div>
        <div style={{textAlign:'right'}}>
          <div className="cap-summary-lbl">Unrealised</div>
          <div className="cap-summary-sub" style={{color:upColor}}>{upnl >= 0 ? '+' : ''}{fmtRs(upnl)}</div>
        </div>
      </div>
      <div>
        <div className="cap-summary-bar-labels">
          <span><strong>{fmtRs(usedCap)}</strong> used</span>
          <span>of {fmtRs(capital)}</span>
        </div>
        <div className="cap-summary-bar-track">
          <div className="cap-summary-bar-fill" style={{width:`${pct}%`}} />
        </div>
      </div>
    </div>
  )
}

// ─── Account picker — own section above the trade list ───────────────────────

function AccountPickerRow({ account, label, onClick, showChevron, expanded }) {
  const isGame = !!account.game_id
  return (
    <div className={`acct-picker-row${onClick ? ' clickable' : ''}`} onClick={onClick}>
      <div className={`acct-picker-icon${isGame ? ' game' : ''}`}>
        {isGame ? <GameIcon /> : <BankIcon />}
      </div>
      <div className="acct-picker-text">
        <div className="acct-picker-name">{label}</div>
        <div className="acct-picker-caption">{isGame ? 'Game account' : 'Broker account'}</div>
      </div>
      {showChevron && <div className="acct-picker-chevron"><ChevronIcon open={expanded} /></div>}
    </div>
  )
}

function AccountPicker({ realAccounts, gameAccounts, acctFilter, setAcct, isAdmin, acctLabel }) {
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState(false)
  const all = [...realAccounts, ...gameAccounts]

  if (all.length === 0) {
    if (isAdmin) {
      return (
        <div className="card">
          <div className="card-body" style={{textAlign:'center',padding:'20px'}}>
            <span style={{fontSize:13,color:'var(--muted)'}}>No accounts found.</span>
          </div>
        </div>
      )
    }
    return (
      <div className="card">
        <div className="card-body" style={{textAlign:'center',padding:'28px 20px'}}>
          <div style={{color:'var(--muted)',display:'flex',justifyContent:'center',marginBottom:10}}><BankIcon size={30}/></div>
          <div style={{fontSize:14,fontWeight:700,marginBottom:6}}>Add your first account</div>
          <div style={{fontSize:13,color:'var(--muted)',marginBottom:18}}>Connect a brokerage account to start tracking your own positions here.</div>
          <button className="btn btn-primary" onClick={() => navigate('/profile/accounts')}>Open Account Settings →</button>
        </div>
      </div>
    )
  }

  // Same preference order as the page-level acctFilter derivation (real
  // account before game account) so the picker never shows a "selected"
  // account that doesn't match what's actually driving the trade list below.
  const selected  = all.find(a => String(a.id) === acctFilter) || realAccounts[0] || gameAccounts[0]
  const others    = all.filter(a => a !== selected)
  const canSwitch = all.length > 1

  // "+ Add another account" must stay reachable regardless of how many
  // accounts exist — it was always visible next to the old <select> (for
  // non-admins) — so it isn't gated behind `canSwitch`/`expanded` alone: a
  // single-account, non-expandable row still gets its own persistent add
  // link; a multi-account row only shows it once expanded (alongside the
  // other accounts to switch to), matching the design canvas.
  return (
    <div className="card acct-picker">
      <AccountPickerRow account={selected} label={acctLabel(selected)}
        onClick={canSwitch ? () => setExpanded(v => !v) : undefined}
        showChevron={canSwitch} expanded={expanded} />
      {!canSwitch && !isAdmin && (
        <button type="button" className="acct-picker-add" onClick={() => navigate('/profile/accounts')}>
          <PlusIcon /> Add another account
        </button>
      )}
      {canSwitch && expanded && (
        <div className="acct-picker-expanded">
          {others.map(a => (
            <AccountPickerRow key={a.id} account={a} label={acctLabel(a)}
              onClick={() => { setAcct(String(a.id)); setExpanded(false) }} />
          ))}
          {!isAdmin && (
            <button type="button" className="acct-picker-add" onClick={() => navigate('/profile/accounts')}>
              <PlusIcon /> Add another account
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ─── New trade form (client) ─────────────────────────────────────────────────

function NewTradeForm({ accounts, gameAccounts, onDone }) {
  const navigate = useNavigate()
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
          <Dropdown variant="form" value={acctId} onChange={setAcctId} placeholder="Select account…"
            groups={[
              { label: 'Broker Accounts', options: accounts.map(a => ({
                  value: String(a.id), label: a.label || [a.broker, a.account_no].filter(Boolean).join(' · ') || `Account ${a.id}` })) },
              { label: 'Game Accounts', options: (gameAccounts||[]).map(a => ({
                  value: String(a.id), label: a.label || `Game #${a.game_id}` })) },
            ]} />
          <button type="button" className="add-account-link" onClick={() => navigate('/profile/accounts')}>
            <span className="add-leg-badge" style={{width:16,height:16}}><PlusIcon size={9}/></span>
            Add
          </button>
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
        <button className="btn btn-ghost" onClick={() => onDone()} style={{color:'var(--muted)'}}>Cancel</button>
      </div>
    </div>
  )
}

// ─── Screen ───────────────────────────────────────────────────────────────────

const SEGMENTS = ['all', 'F&O', 'Equity', 'ETF', 'Commodities']

// Mirrors Dashboard.jsx's RISK_LEVELS/RISK_LABEL — kept as a separate
// per-screen constant rather than a shared import, matching how SEGMENTS
// above is already duplicated rather than extracted.
const RISK_LEVELS = [
  { value: 'low',       label: 'Low' },
  { value: 'mid',       label: 'Mid' },
  { value: 'high',      label: 'High' },
  { value: 'very_high', label: 'Very High' },
]
const RISK_LABEL = Object.fromEntries(RISK_LEVELS.map(r => [r.value, r.label]))

export default function Positions() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const user     = useAuthStore(s => s.user)
  const isAdmin  = user?.role === 'super_admin' || user?.role === 'admin'

  const [posTab, setPosTab]                 = useState('open')
  const [segment, setSegment]               = useState('all')
  const [risk,    setRisk]                  = useState('all')
  const { data: accounts = [], isLoading: acctsLoading } = useAccounts()

  const realAccounts = accounts.filter(a => !a.game_id)
  const gameAccounts = accounts.filter(a => a.game_id && a.game_status === 'active')

  // Account ids are always positive integers (SQLite autoincrement) — reject
  // anything else, so a corrupted localStorage value can never reach
  // useTrades/useTradeHistory's `params`.
  const isValidAcctId = v => /^\d+$/.test(v)

  // ?account= — set by Dashboard after a push-to-account, so landing here
  // selects the account that was just pushed to instead of defaulting to the
  // first one (this used to be an in-place auto-switch when Positions was a
  // sibling panel rather than its own route — see Dashboard.jsx's
  // handlePushed). Read directly from the URL (available synchronously,
  // unlike `accounts`), so it's already part of the very first render's
  // derivation below — no effect-driven correction/race needed for the
  // value itself. The effect further down only cleans up the URL param and
  // persists the choice, it doesn't gate anything.
  const navAcct = searchParams.get('account')

  // acctFilter is DERIVED, not stored as its own state — computed fresh every
  // render from whatever's currently known (?account= param, else manual
  // selection this session, else localStorage, else the first real account),
  // and only once `accounts` has actually loaded (`enabled: !acctsLoading`
  // below). Previously this was read from localStorage once via useState at
  // mount, then "corrected" by a useEffect after accounts loaded — which
  // meant the very first render always fired a request with whatever the
  // pre-accounts-load guess was (nothing, or a stale/invalid value), before
  // the effect could catch up. Deriving it during render and gating the
  // queries on accounts having loaded closes that race outright instead of
  // shortening it.
  const [manualAcct, setManualAcct] = useState(null)
  const storedAcct = (() => {
    const v = localStorage.getItem('ev_acct')
    return v && isValidAcctId(v) ? v : null
  })()

  let acctFilter = ''
  if (accounts.length > 0) {
    const validIds  = [...realAccounts, ...gameAccounts].map(a => String(a.id))
    const preferred = navAcct ?? manualAcct ?? storedAcct
    acctFilter = preferred && validIds.includes(preferred) ? preferred
               : realAccounts.length ? String(realAccounts[0].id) : ''
  }

  // Persist the ?account= choice (so it survives after the param is cleared)
  // and clean the URL so a later manual reload doesn't keep re-forcing it.
  useEffect(() => {
    if (!navAcct) return
    setAcct(navAcct)
    setSearchParams(p => { p.delete('account'); return p }, { replace: true })
  }, [navAcct])  // eslint-disable-line react-hooks/exhaustive-deps

  function setAcct(id) {
    setManualAcct(id || null)
    if (id && isValidAcctId(String(id))) localStorage.setItem('ev_acct', String(id))
    else localStorage.removeItem('ev_acct')
  }

  const params    = acctFilter ? { account_id: acctFilter } : undefined
  const dataReady = !acctsLoading
  const { data: trades = [], isLoading, refetch }  = useTrades(params, dataReady)
  const { data: history = [], isLoading: histLoad, refetch: refetchHist } = useTradeHistory(params, dataReady && posTab === 'history')

  const instrKeys = [...new Set(trades.flatMap(t => {
    const allLegs = [...(t.legs || []), ...(t.applied_adjustments || []).flatMap(a => a.legs || [])]
    return allLegs.map(l => l.instrument_key).filter(Boolean)
  }))]
  const { data: prices = {} } = useRecPrices(instrKeys)

  const title = isAdmin ? 'All Positions' : 'My Positions'

  const list        = posTab === 'history' ? history : trades
  const usedSegs    = new Set(list.map(t => t.segment))

  const bySegment = segment === 'all' ? { trades, history } :
    { trades: trades.filter(t => t.segment === segment), history: history.filter(t => t.segment === segment) }
  const byRisk = risk === 'all' ? bySegment :
    { trades: bySegment.trades.filter(t => t.risk_level === risk), history: bySegment.history.filter(t => t.risk_level === risk) }
  const filteredTrades  = byRisk.trades
  const filteredHistory = byRisk.history

  function acctLabel(a) {
    const base = a.label || [a.broker, a.account_no].filter(Boolean).join(' · ') || `Account ${a.id}`
    return a.user_name ? `${a.user_name} · ${base}` : base
  }

  return (
    <div className="positions-layout">
      <PageHeader title={title} showBack={false} />

      <AccountPicker realAccounts={realAccounts} gameAccounts={gameAccounts}
        acctFilter={acctFilter} setAcct={setAcct} isAdmin={isAdmin} acctLabel={acctLabel} />

      {acctFilter && <CapitalSummary accountId={parseInt(acctFilter)} />}

      <div className="card">
        {!isAdmin && (
          <div className="card-header">
            <button className={`pos-tab-new${posTab==='new'?' active':''}`}
                    onClick={()=>setPosTab(posTab === 'new' ? 'open' : 'new')}>
              + New Trade
            </button>
            {posTab === 'new' && (
              <button className="btn btn-ghost btn-sm" style={{marginLeft:'auto',display:'inline-flex'}}
                      onClick={()=>setPosTab('open')}><CloseIcon/></button>
            )}
          </div>
        )}

        {posTab !== 'new' && (
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
              <Dropdown value={posTab} onChange={setPosTab} align="right"
                options={[
                  {value:'open', label:<><span className="status-dot status-dot-open" style={{marginRight:6}}/>Open</>},
                  {value:'history', label:<><span className="status-dot status-dot-exited" style={{marginRight:6}}/>History</>},
                ]} />
              <button className="btn btn-ghost btn-sm" style={{display:'inline-flex'}} onClick={()=>posTab==='open'?refetch():refetchHist()}><RefreshIcon/></button>
            </div>
          </div>
        )}

        <div className="card-body" style={{padding:10}}>
          {posTab === 'new' && (
            <NewTradeForm accounts={realAccounts} gameAccounts={gameAccounts} onDone={id => { if (id) setAcct(String(id)); setPosTab('open'); refetch() }} />
          )}
          {posTab === 'open' && (
            isLoading ? <div className="empty">Loading…</div> :
            !filteredTrades.length ? <div className="empty">No {segment !== 'all' ? segment + ' ' : ''}open positions.</div> :
            <div style={{display:'flex',flexDirection:'column',gap:12}}>
              {filteredTrades.map(t => <TradeCard key={t.id} trade={t} isAdmin={isAdmin} prices={prices} />)}
            </div>
          )}
          {posTab === 'history' && (
            histLoad ? <div className="empty">Loading…</div> :
            !filteredHistory.length ? <div className="empty">No {segment !== 'all' ? segment + ' ' : ''}closed trades.</div> :
            <div style={{display:'flex',flexDirection:'column',gap:12}}>
              {filteredHistory.map(t => <HistoryCard key={t.id} trade={t} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
