import { useState } from 'react'
import { useGame, useSubmitEntry, useResolveGame, useActivateGame, useCloseGame,
         useDeleteGame, usePortfolio, useSubmitVirtualTrade } from '../../hooks/useGames'
import useAuthStore from '../../store/authStore'
import usePrices from '../../hooks/usePrices'
import { useToast } from '../common/Toast'
import './GameDetail.css'

const TYPE_LABEL = { price_prediction:'🔮 Prediction', mcq:'📝 Quiz', leaderboard:'📈 Leaderboard' }
const TYPE_CLASS = { price_prediction:'gtype-prediction', mcq:'gtype-mcq', leaderboard:'gtype-leaderboard' }

function fmtRs(v, dec=0) {
  if (v == null) return '—'
  return '₹' + Number(v).toLocaleString('en-IN', { maximumFractionDigits: dec })
}
function fmtIst(ts) {
  if (!ts) return ''
  const d = new Date(ts.replace('Z','') + (ts.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString('en-IN', { timeZone:'Asia/Kolkata', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', hour12:true })
}

export default function GameDetail({ id, onEdit }) {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const { data: game, isLoading } = useGame(id)

  if (isLoading) return <div className="games-empty">Loading…</div>
  if (!game)     return <div className="games-empty">Game not found.</div>

  const statusChip = {
    draft:    <span className="status-chip chip-draft">Draft</span>,
    active:   <span className="status-chip chip-active">🟢 Live</span>,
    closed:   <span className="status-chip chip-closed">Closed</span>,
    resolved: <span className="status-chip chip-resolved">✅ Resolved</span>,
  }[game.status]

  return (
    <div>
      <div className="game-detail-card">
        <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',gap:12,marginBottom:10}}>
          <div style={{flex:1}}>
            <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:6}}>
              <span className={`game-type-badge ${TYPE_CLASS[game.game_type]||''}`}>{TYPE_LABEL[game.game_type]||game.game_type}</span>
              {statusChip}
            </div>
            <h2 style={{fontSize:16,fontWeight:700,color:'#1e293b',lineHeight:1.3}}>{game.title}</h2>
          </div>
        </div>

        {game.description && <p style={{fontSize:13,color:'#475569',marginBottom:14,lineHeight:1.5}}>{game.description}</p>}

        <div className="game-meta-bar">
          <span>⏰ Ends {fmtIst(game.end_time)}</span>
          <span>💎 {game.reward_pool} credits pool</span>
          <span>🏆 Top {game.winner_count} win</span>
          <span>👥 {game.participant_count} participants</span>
        </div>

        {game.game_type === 'price_prediction' && <PredictionGame game={game} isAdmin={isAdmin} user={user} />}
        {game.game_type === 'mcq'              && <McqGame         game={game} isAdmin={isAdmin} user={user} />}
        {game.game_type === 'leaderboard'      && <LeaderboardGame game={game} isAdmin={isAdmin} />}

        {!isAdmin && ['active','closed'].includes(game.status) && !game.my_entry && <ParticipantTeaser game={game} />}
        {!isAdmin && ['active','closed'].includes(game.status) &&  game.my_entry && <ParticipantsPanel game={game} userId={user?.id} />}

        {isAdmin && <AdminActions game={game} onEdit={onEdit} />}
      </div>

      {(isAdmin || ['closed','resolved'].includes(game.status)) && <LeaderboardSection game={game} />}
    </div>
  )
}

// ─── Prediction game ──────────────────────────────────────────────────────────

function PredictionGame({ game, isAdmin, user }) {
  const sym    = game.symbol || 'NIFTY50'
  const { data: { spot } = { spot: {} } } = usePrices()
  const refLtp = spot[sym]?.ltp ?? null
  const step   = sym.includes('BANK') ? 100 : 50
  const [val,     setVal]     = useState('')
  const [locked,  setLocked]  = useState(false)
  const submit = useSubmitEntry(game.id)
  const toast  = useToast()

  if (isAdmin) {
    return (
      <div style={{fontSize:12,color:'#64748b',padding:'10px 0'}}>
        Symbol: <strong style={{color:'#1e293b'}}>{sym}</strong>
        {game.status === 'resolved' && game.result_value &&
          <> · Actual close: <strong style={{color:'#15803d'}}>{fmtRs(game.result_value,2)}</strong></>}
        {game.status === 'closed' && !game.result_value &&
          <> · Awaiting resolution — enter actual close price below.</>}
      </div>
    )
  }

  const entry = game.my_entry
  const pp    = entry?.entry_data?.predicted_price
  if (locked && !pp) return <div style={{border:'1px solid #bfdbfe',background:'#eff6ff',borderRadius:10,padding:16,marginBottom:4,fontSize:13,color:'#1d4ed8',fontWeight:600}}>Prediction locked! Updating…</div>

  if (pp != null) {
    const actual = game.status === 'resolved' && game.result_value ? parseFloat(game.result_value) : null
    const diff   = actual != null ? Math.abs(parseFloat(pp) - actual) : null
    return (
      <div style={{border:'1px solid #bfdbfe',background:'#eff6ff',borderRadius:10,padding:16,marginBottom:4}}>
        <div style={{fontSize:11,fontWeight:700,color:'#1d4ed8',textTransform:'uppercase',letterSpacing:.4,marginBottom:8}}>Your Entry</div>
        <div style={{fontSize:20,fontWeight:700,color:'#1e293b',marginBottom:4}}>{fmtRs(pp,2)}</div>
        <div style={{fontSize:12,color:'#64748b'}}>Predicted close for {sym}</div>
        {actual != null ? (
          <div style={{marginTop:12,paddingTop:12,borderTop:'1px solid #bfdbfe',display:'flex',gap:20,flexWrap:'wrap'}}>
            <div><div style={{fontSize:11,color:'#64748b'}}>Actual close</div><div style={{fontSize:14,fontWeight:600,color:'#1e293b'}}>{fmtRs(actual,2)}</div></div>
            <div><div style={{fontSize:11,color:'#64748b'}}>Difference</div><div style={{fontSize:14,fontWeight:600,color:diff<100?'#15803d':'#dc2626'}}>±{fmtRs(diff,2)}</div></div>
            {entry.rank  && <div><div style={{fontSize:11,color:'#64748b'}}>Your rank</div><div style={{fontSize:14,fontWeight:700,color:'#d97706'}}>#{entry.rank}</div></div>}
            {entry.credits_won && <div><div style={{fontSize:11,color:'#64748b'}}>Credits won</div><div style={{fontSize:14,fontWeight:700,color:'#fbbf24'}}>💎 {entry.credits_won}</div></div>}
          </div>
        ) : (
          <div style={{marginTop:8,fontSize:12,color:'#64748b'}}>{entry.rank ? `Rank #${entry.rank}` : 'Waiting for results…'}</div>
        )}
      </div>
    )
  }

  if (game.status !== 'active') {
    return <div className="game-closed-msg">Game is {game.status} — entries closed</div>
  }

  const refFmt = refLtp != null ? fmtRs(refLtp) : '—'
  const numVal = parseFloat(val)
  const sentiment = numVal && refLtp
    ? (() => {
        const diff = numVal - refLtp
        const pct  = ((diff / refLtp) * 100).toFixed(2)
        const up   = diff >= 0
        return {
          text:  `${up ? '📈 +' : '📉 '}${pct}% ${up ? 'above' : 'below'} current · ${up ? 'Bullish' : 'Bearish'}`,
          color: up ? '#16a34a' : '#dc2626'
        }
      })()
    : null

  function nudge(delta) {
    const base = parseFloat(val) || refLtp || 0
    setVal(String(Math.max(0, Math.round((base + delta) / step) * step)))
  }

  async function lock() {
    const price = parseFloat(val)
    if (!price) return toast('Enter a price', 'err')
    const res = await submit.mutateAsync({ entry_data: { predicted_price: price } })
    if (res.ok) { setLocked(true); toast('Prediction locked! 🎯', 'ok') }
    else toast(res.error || 'Error', 'err')
  }

  return (
    <div className="pred-ui">
      <div className="pred-ref">
        <div className="pred-ref-sym">{sym} · live</div>
        <div className="pred-ref-ltp">{refFmt}</div>
        <div className="pred-ref-lbl">Where will it close today?</div>
      </div>
      <div className="pred-divider" />
      <div className="pred-nudge-row">
        <button className="pred-nudge neg" onClick={()=>nudge(-step*10)}>−{step*10}</button>
        <button className="pred-nudge neg" onClick={()=>nudge(-step)}>−{step}</button>
        <div className="pred-center">
          <div className="pred-val-label">Your prediction</div>
          <input type="number" className="pred-big-input" value={val}
            placeholder={refLtp ? String(Math.round(refLtp)) : '24000'}
            onChange={e=>setVal(e.target.value)} step={step} />
          <div className="pred-sentiment" style={{color: sentiment?.color || '#94a3b8'}}>
            {sentiment?.text || 'Enter a price above ↑'}
          </div>
        </div>
        <button className="pred-nudge pos" onClick={()=>nudge(step)}>+{step}</button>
        <button className="pred-nudge pos" onClick={()=>nudge(step*10)}>+{step*10}</button>
      </div>
      <button className="btn btn-primary pred-submit-btn" onClick={lock} disabled={submit.isPending}>
        Lock in my prediction →
      </button>
      <div style={{fontSize:11,color:'#94a3b8',textAlign:'center'}}>Closest prediction wins · One entry only</div>
    </div>
  )
}

// ─── MCQ game ─────────────────────────────────────────────────────────────────

function McqGame({ game, isAdmin }) {
  const [sel, setSel] = useState({})
  const submit = useSubmitEntry(game.id)
  const toast  = useToast()

  if (!game.questions?.length) return <div className="game-closed-msg">No questions added yet</div>

  const isResolved = game.status === 'resolved'
  const myAnswers  = game.my_entry?.entry_data?.answers || {}
  const submitted  = !!game.my_entry
  const locked     = submitted || isResolved || isAdmin
  const activeSel  = submitted ? myAnswers : sel

  async function doSubmit() {
    const answered = Object.keys(activeSel).length
    if (!answered) return toast('Answer at least one question', 'err')
    const res = await submit.mutateAsync({ entry_data: { answers: activeSel } })
    if (res.ok) toast('Answers submitted!', 'ok')
    else toast(res.error || 'Error', 'err')
  }

  const score     = game.my_entry?.score
  const rank      = game.my_entry?.rank
  const won       = game.my_entry?.credits_won
  const answeredN = Object.keys(activeSel).length

  return (
    <div>
      {submitted && !isResolved && (
        <div style={{padding:'12px 16px',background:'#dcfce7',border:'1px solid #86efac',borderRadius:8,marginBottom:14,display:'flex',alignItems:'center',gap:10}}>
          <span style={{fontSize:20}}>✅</span>
          <div>
            <div style={{fontSize:13,fontWeight:700,color:'#15803d'}}>Answers locked in!</div>
            <div style={{fontSize:12,color:'#166534'}}>{Object.keys(myAnswers).length}/{game.questions.length} answered · Waiting for results</div>
          </div>
        </div>
      )}
      {isResolved && submitted && (
        <div style={{padding:'14px 16px',background:'linear-gradient(135deg,#fef3c7,#fefce8)',border:'1px solid #fcd34d',borderRadius:10,marginBottom:14}}>
          <div style={{fontSize:11,fontWeight:700,color:'#92400e',marginBottom:8,textTransform:'uppercase',letterSpacing:.4}}>Your result</div>
          <div style={{display:'flex',gap:20,flexWrap:'wrap'}}>
            <div><div style={{fontSize:11,color:'#78350f'}}>Score</div><div style={{fontSize:22,fontWeight:800,color:'#1e293b'}}>{score != null ? Math.round(score) : '?'}<span style={{fontSize:14,color:'#94a3b8'}}>/{game.questions.length}</span></div></div>
            {rank && <div><div style={{fontSize:11,color:'#78350f'}}>Rank</div><div style={{fontSize:22,fontWeight:800,color:'#d97706'}}>#{rank}</div></div>}
            {won  && <div><div style={{fontSize:11,color:'#78350f'}}>Credits won</div><div style={{fontSize:22,fontWeight:800,color:'#f59e0b'}}>💎{won}</div></div>}
          </div>
        </div>
      )}

      {!locked && (
        <div className="mcq-progress">
          {game.questions.map(q => (
            <div key={q.id} className={`mcq-prog-dot${activeSel[String(q.id)] ? ' answered' : ''}`} />
          ))}
        </div>
      )}

      {game.questions.map((q, i) => {
        const myAns = activeSel[String(q.id)]
        const opts  = ['a','b','c','d'].filter(o => q[`option_${o}`])
        return (
          <div key={q.id} className="mcq-question">
            <div className="mcq-q-text">Q{i+1}. {q.question}</div>
            {opts.map(o => {
              const opt = o.toUpperCase()
              const isMyAns = opt === myAns
              let cls = isMyAns ? 'sel' : ''
              let icon = null
              if (isResolved && q.correct_opt) {
                if (opt === q.correct_opt)               { cls = 'correct-ans'; icon = '✅' }
                else if (isMyAns && opt !== q.correct_opt){ cls = 'wrong-ans';  icon = '❌' }
              }
              return (
                <div key={o}
                  className={`mcq-opt-card ${cls}${locked?' disabled':''}`}
                  onClick={locked ? undefined : () => setSel(s => ({...s, [String(q.id)]: opt}))}>
                  <span className="mcq-opt-letter">{opt}</span>
                  <span className="mcq-opt-text">{q[`option_${o}`]}</span>
                  {icon && <span className="mcq-opt-icon">{icon}</span>}
                </div>
              )
            })}
          </div>
        )
      })}

      {!submitted && game.status === 'active' && !isAdmin && (
        <button className="btn btn-primary" style={{width:'100%',padding:12,fontSize:14,fontWeight:700,borderRadius:10,justifyContent:'center'}}
          onClick={doSubmit} disabled={submit.isPending}>
          Submit all answers →
        </button>
      )}
    </div>
  )
}

// ─── Leaderboard game ─────────────────────────────────────────────────────────

function LeaderboardGame({ game, isAdmin }) {
  const e      = game.my_entry
  const rank   = e?.rank
  const won    = e?.credits_won
  const submit = useSubmitEntry(game.id)
  const toast  = useToast()

  if (isAdmin) return null

  if (game.status === 'resolved') {
    return (
      <div style={{border:'1px solid #bfdbfe',background:'#eff6ff',borderRadius:10,padding:16,marginBottom:4}}>
        <div style={{fontSize:11,fontWeight:700,color:'#1d4ed8',textTransform:'uppercase',letterSpacing:.4,marginBottom:8}}>Your Result</div>
        {rank ? (
          <div style={{display:'flex',gap:20,flexWrap:'wrap'}}>
            <div><div style={{fontSize:11,color:'#64748b'}}>Final rank</div><div style={{fontSize:20,fontWeight:700,color:'#d97706'}}>#{rank}</div></div>
            {won && <div><div style={{fontSize:11,color:'#64748b'}}>Credits won</div><div style={{fontSize:20,fontWeight:700,color:'#fbbf24'}}>💎 {won}</div></div>}
          </div>
        ) : <div style={{fontSize:13,color:'#64748b'}}>Check the final leaderboard below.</div>}
      </div>
    )
  }

  if (game.status === 'active' && !e) {
    async function doJoin() {
      const res = await submit.mutateAsync({})
      if (res.ok) toast('Joined! Your virtual account is ready.', 'ok')
      else toast(res.error || 'Error joining', 'err')
    }
    return (
      <div style={{background:'#f8fafc',border:'1px solid #e2e8f0',borderRadius:10,padding:20,textAlign:'center',marginBottom:4}}>
        <div style={{fontSize:15,fontWeight:700,color:'#1e293b',marginBottom:6}}>Join the Trading Challenge</div>
        <div style={{fontSize:13,color:'#64748b',marginBottom:16}}>
          A virtual account with starting capital will be created for you.<br/>
          Push recommendations from the Dashboard to trade.
        </div>
        <button className="btn btn-primary" style={{padding:'10px 28px',fontSize:14,fontWeight:700,borderRadius:8}}
          onClick={doJoin} disabled={submit.isPending}>
          {submit.isPending ? 'Joining…' : 'Join Game →'}
        </button>
      </div>
    )
  }

  if (['active','closed'].includes(game.status) && e) return <PortfolioView gid={game.id} />

  return <div className="game-closed-msg">Game is {game.status} — trading closed</div>
}

function PortfolioView({ gid }) {
  const { data, isLoading, refetch } = usePortfolio(gid)

  if (isLoading) return <div style={{padding:20,textAlign:'center',color:'#94a3b8',fontSize:13}}>Loading portfolio…</div>

  const pf        = data?.portfolio || {}
  const positions = pf.positions || []
  const pnl       = pf.pnl || 0
  const pnlColor  = pnl >= 0 ? '#16a34a' : '#dc2626'

  if (!pf.account_id) {
    return (
      <div style={{background:'#f8fafc',border:'1px solid #e2e8f0',borderRadius:8,padding:20,textAlign:'center'}}>
        <div style={{fontSize:13,color:'#64748b'}}>Setting up your virtual account…</div>
        <button className="btn btn-ghost btn-sm" onClick={refetch} style={{marginTop:8}}>↻ Refresh</button>
      </div>
    )
  }

  return (
    <div>
      {/* Account reference header */}
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:10}}>
        <span style={{fontSize:13,fontWeight:600,color:'#1e293b'}}>
          {pf.label || `Virtual Account #${pf.account_id}`}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={refetch} style={{padding:'3px 8px',fontSize:11}}>↻</button>
      </div>

      <div className="portfolio-bar">
        <div className="portfolio-stat">
          <div className="val">{fmtRs(pf.capital)}</div>
          <div className="lbl">Capital</div>
        </div>
        <div className="portfolio-stat">
          <div className="val" style={{color: pf.unrealized_pnl >= 0 ? '#16a34a' : '#dc2626'}}>
            {pf.unrealized_pnl >= 0 ? '+' : ''}{fmtRs(pf.unrealized_pnl)}
          </div>
          <div className="lbl">Unrealized P&amp;L</div>
        </div>
        <div className="portfolio-stat">
          <div className="val" style={{color:pnlColor,fontWeight:700}}>
            {pnl >= 0 ? '+' : ''}{fmtRs(pnl)}
          </div>
          <div className="lbl">Total P&amp;L</div>
        </div>
      </div>

      {positions.length ? (
        <table className="leaderboard-table" style={{marginBottom:10}}>
          <thead><tr><th>Symbol</th><th>Side</th><th>Legs</th><th>Entry</th><th>LTP</th><th>P&amp;L</th></tr></thead>
          <tbody>
            {positions.map((p, i) => {
              const leg = `${p.strike ? Number(p.strike).toLocaleString('en-IN') + ' ' : ''}${p.instrument_type}${p.expiry_str ? ' ' + p.expiry_str : ''}`
              const qty = (p.lots || 0) * (p.lot_size || 1)
              return (
                <tr key={i}>
                  <td style={{fontWeight:600}}>{p.symbol}</td>
                  <td><span className={`leg-pill ${p.side==='BUY'?'leg-pill-buy':'leg-pill-sell'}`}>{p.side}</span></td>
                  <td style={{fontSize:11,color:'#64748b'}}>{leg} · {p.lots}L ({qty})</td>
                  <td>{fmtRs(p.entry_price, 2)}</td>
                  <td>{p.ltp != null ? fmtRs(p.ltp, 2) : '—'}</td>
                  <td><span style={{color:p.pnl>=0?'#16a34a':'#dc2626',fontWeight:600}}>{p.pnl>=0?'+':''}{fmtRs(p.pnl)}</span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      ) : (
        <div style={{fontSize:12,color:'#94a3b8',padding:'12px 0',marginBottom:4}}>
          No open positions · add trades from the Dashboard
        </div>
      )}
    </div>
  )
}

// ─── Participant teaser ───────────────────────────────────────────────────────

function ParticipantTeaser({ game }) {
  const n = game.participant_count || 0
  if (!n) return null
  return (
    <div className="pax-teaser">
      <div className="pax-teaser-icon">👀</div>
      <div>
        <div className="pax-teaser-count">{n === 1 ? '1 person has already entered' : `${n} people have already entered`}</div>
        <div className="pax-teaser-sub">Submit your entry to see who's in — predictions stay hidden until results!</div>
      </div>
    </div>
  )
}

// ─── Participants panel ───────────────────────────────────────────────────────

function ParticipantsPanel({ game, userId }) {
  const { data: { spot } = { spot: {} } } = usePrices()
  const entries = game.entries || []
  if (!entries.length) return null

  const total   = entries.length
  const shown   = entries.slice(0, 20)
  const overflow= total - 20
  const isPred  = game.game_type === 'price_prediction'
  const refLtp  = isPred ? (spot[game.symbol || 'NIFTY50']?.ltp ?? null) : null
  const note    = isPred ? '📈 predictions visible after entry · final score after close' : '🔒 answers hidden until results'

  const getPredPrice = e => e.predicted_price ?? e.entry_data?.predicted_price ?? null
  const bulls = isPred && refLtp ? entries.filter(e => { const p = getPredPrice(e); return p != null && parseFloat(p) >= refLtp }).length : 0
  const bears = isPred && refLtp ? entries.filter(e => { const p = getPredPrice(e); return p != null && parseFloat(p) <  refLtp }).length : 0
  const bullPct = total ? Math.round((bulls / total) * 100) : 0

  return (
    <div className="participants-panel">
      <div className="participants-panel-hdr">
        <span className="participants-panel-title">👥 {total} participant{total===1?'':'s'} in this game</span>
        <span className="participants-panel-note">{note}</span>
      </div>

      {isPred && refLtp && (
        <div style={{padding:'10px 14px',borderBottom:'1px solid #e2e8f0',background:'#f8fafc'}}>
          <div style={{fontSize:10,fontWeight:700,color:'#64748b',marginBottom:6,textTransform:'uppercase',letterSpacing:.4}}>Crowd sentiment</div>
          <div style={{display:'flex',borderRadius:6,overflow:'hidden',height:8,marginBottom:5}}>
            <div style={{width:`${bullPct}%`,background:'#16a34a',transition:'width .4s'}} />
            <div style={{width:`${100-bullPct}%`,background:'#dc2626',transition:'width .4s'}} />
          </div>
          <div style={{display:'flex',justifyContent:'space-between',fontSize:11,fontWeight:600}}>
            <span style={{color:'#16a34a'}}>📈 Bullish {bullPct}% ({bulls})</span>
            <span style={{color:'#dc2626'}}>{bears} ({100-bullPct}%) Bearish 📉</span>
          </div>
        </div>
      )}

      {shown.map((e, i) => {
        const isMe = e.user_id === userId
        const pp   = isPred ? (v => v != null ? parseFloat(v) : null)(getPredPrice(e)) : null
        const up   = pp != null && refLtp != null ? pp >= refLtp : null
        const pct  = pp != null && refLtp ? ` (${up?'+':''}${((pp - refLtp)/refLtp*100).toFixed(1)}%)` : ''
        const col  = up === null ? '#64748b' : (up ? '#16a34a' : '#dc2626')
        const arrow= up === null ? '' : (up ? '▲' : '▼')

        return (
          <div key={e.user_id} className={`participant-row${isMe?' me':''}`}>
            <span className="p-num">{i+1}</span>
            <span className="p-avatar">{(e.user_name||'?')[0].toUpperCase()}</span>
            <span className="p-name">{e.user_name||'?'}{isMe && <span className="p-you-badge">YOU</span>}</span>
            {isPred && pp != null && <span style={{fontSize:12,fontWeight:700,color:col,flexShrink:0}}>{arrow} {fmtRs(pp)}{pct}</span>}
            {isPred && pp == null && <span style={{fontSize:11,color:'#94a3b8'}}>—</span>}
            <span className="p-time">{fmtIst(e.submitted_at)}</span>
          </div>
        )
      })}
      {overflow > 0 && <div className="participant-row" style={{justifyContent:'center',color:'#94a3b8',fontSize:12,padding:10}}>+{overflow} more</div>}
    </div>
  )
}

// ─── Leaderboard section (admin + resolved) ───────────────────────────────────

function LeaderboardSection({ game }) {
  const entries   = game.entries || []
  const title     = game.status === 'resolved' ? '🏆 Final Results' : '📋 Participants'
  const scoreLabel= game.game_type === 'price_prediction' ? 'Diff' : game.game_type === 'mcq' ? 'Score' : 'P&L'

  function scoreFmt(e) {
    if (game.game_type === 'price_prediction') return e.score != null ? `±${parseFloat(e.score).toLocaleString('en-IN',{maximumFractionDigits:1})}` : '—'
    if (game.game_type === 'mcq') return e.score != null ? `${e.score} correct` : '—'
    return e.score != null ? (e.score >= 0 ? '+' : '') + fmtRs(e.score) : '—'
  }

  return (
    <div className="game-detail-card">
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
        <span style={{fontSize:12,fontWeight:700,color:'#1e293b'}}>{title}</span>
        <span style={{fontSize:11,color:'#94a3b8'}}>{entries.length} {entries.length===1?'entry':'entries'}</span>
      </div>
      {!entries.length
        ? <div style={{color:'#94a3b8',fontSize:13,padding:'10px 0'}}>No entries yet</div>
        : (
          <table className="leaderboard-table">
            <thead><tr><th>Rank</th><th>Name</th><th>{scoreLabel}</th>{game.status==='resolved' && <th>Credits</th>}</tr></thead>
            <tbody>
              {entries.map(e => (
                <tr key={e.user_id}>
                  <td>{e.rank <= 3
                    ? <span className={`rank-badge rank-${e.rank}`}>{['🥇','🥈','🥉'][e.rank-1]}</span>
                    : <span className="rank-badge">{e.rank||'—'}</span>}
                  </td>
                  <td style={{fontWeight:500}}>{e.user_name||'—'}</td>
                  <td>{scoreFmt(e)}</td>
                  {game.status==='resolved' && <td>{e.credits_won ? <span style={{color:'#d97706',fontWeight:700}}>💎{e.credits_won}</span> : '—'}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        )
      }
    </div>
  )
}

// ─── Admin actions ────────────────────────────────────────────────────────────

function AdminActions({ game, onEdit }) {
  const toast    = useToast()
  const activate = useActivateGame(game.id)
  const close    = useCloseGame(game.id)
  const resolve  = useResolveGame(game.id)
  const del      = useDeleteGame()
  const [resolvePrice, setResolvePrice] = useState('')

  async function doActivate() {
    const res = await activate.mutateAsync()
    if (res.ok) toast('Game activated!', 'ok')
    else toast(res.error||'Error', 'err')
  }
  async function doClose() {
    const res = await close.mutateAsync()
    if (res.ok) toast('Game closed!', 'ok')
    else toast(res.error||'Error', 'err')
  }
  async function doResolve() {
    const body = game.game_type === 'price_prediction' ? { result_value: parseFloat(resolvePrice) } : {}
    const res  = await resolve.mutateAsync(body)
    if (res.ok) toast(`Resolved! ${res.winners} winner(s) credited.`, 'ok')
    else toast(res.error||'Error', 'err')
  }
  async function doDelete() {
    if (!confirm('Delete this game?')) return
    const res = await del.mutateAsync(game.id)
    if (res.ok) toast('Game deleted', 'ok')
    else toast(res.error||'Error', 'err')
  }

  return (
    <div className="game-action-bar">
      {(game.status === 'draft' || game.status === 'active') && (
        <button className="btn btn-ghost btn-sm" onClick={() => onEdit(game)}>✏ Edit</button>
      )}
      {game.status === 'draft' && <>
        <button className="btn btn-success btn-sm" onClick={doActivate} disabled={activate.isPending}>▶ Activate</button>
        <button className="btn btn-ghost btn-sm" style={{color:'var(--red)'}} onClick={doDelete}>🗑 Delete</button>
      </>}
      {game.status === 'active' && (
        <button className="btn btn-danger btn-sm" onClick={doClose} disabled={close.isPending}>⏹ Close Game</button>
      )}
      {game.status === 'closed' && <>
        {game.game_type === 'price_prediction' && (
          <input type="number" placeholder="Actual close price" value={resolvePrice}
            onChange={e=>setResolvePrice(e.target.value)} style={{width:170,display:'inline-block'}} />
        )}
        <button className="btn btn-primary btn-sm" onClick={doResolve} disabled={resolve.isPending}>
          ✅ Resolve &amp; Award Credits
        </button>
      </>}
    </div>
  )
}
