import { useState } from 'react'
import { useGames, useCreateGame, useUpdateGame } from '../hooks/useGames'
import { useQuery } from '@tanstack/react-query'
import { getCredits } from '../api/games'
import useAuthStore from '../store/authStore'
import GameDetail from '../components/games/GameDetail'
import { useToast } from '../components/common/Toast'
import './Games.css'

const STATUS_DOT = { draft:'#94a3b8', active:'#4ade80', closed:'#f87171', resolved:'#fbbf24' }
const TYPE_LABEL = { price_prediction:'🔮 Prediction', mcq:'📝 Quiz', leaderboard:'📈 Leaderboard' }
const TYPE_CLASS = { price_prediction:'gtype-prediction', mcq:'gtype-mcq', leaderboard:'gtype-leaderboard' }

const CLIENT_FILTERS = ['active','closed','resolved']
const ADMIN_FILTERS  = ['all','draft','active','closed','resolved']
const FILTER_LABEL   = { all:'All', draft:'Draft', active:'Live', closed:'Closed', resolved:'Resolved' }

const SYMBOLS = ['NIFTY50','BANKNIFTY','FINNIFTY','MIDCPNIFTY','SENSEX']

function fmtIst(ts) {
  if (!ts) return ''
  const d = new Date(ts.replace('Z','') + (ts.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString('en-IN', { timeZone:'Asia/Kolkata', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', hour12:true })
}

function utcToLocalInput(utcStr) {
  if (!utcStr) return ''
  const d = new Date(utcStr.replace('Z','') + (utcStr.endsWith('Z') ? '' : 'Z'))
  const pad = n => String(n).padStart(2,'0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function localInputToUtc(localStr) {
  if (!localStr) return ''
  return new Date(localStr).toISOString()
}

// ─── MCQ question builder ─────────────────────────────────────────────────────

function QuestionBuilder({ questions, onChange }) {
  function add() {
    onChange([...questions, { question:'', option_a:'', option_b:'', option_c:'', option_d:'', correct_opt:'A' }])
  }
  function remove(i) { onChange(questions.filter((_, j) => j !== i)) }
  function update(i, field, val) {
    onChange(questions.map((q, j) => j === i ? { ...q, [field]: val } : q))
  }

  return (
    <div>
      {questions.map((q, i) => (
        <div key={i} style={{border:'1px solid var(--border)',borderRadius:8,padding:'10px 10px 8px',marginBottom:10,background:'#fafafa',position:'relative'}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:8}}>
            <span style={{fontSize:11,fontWeight:700,color:'var(--muted)',textTransform:'uppercase',letterSpacing:.5}}>Question {i+1}</span>
            <button style={{background:'none',border:'none',color:'#cbd5e1',cursor:'pointer',fontSize:16,padding:0}} onClick={() => remove(i)}>✕</button>
          </div>
          <div className="form-row" style={{marginBottom:8}}>
            <input placeholder="Question text" value={q.question} onChange={e=>update(i,'question',e.target.value)} />
          </div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:6,marginBottom:8}}>
            {['a','b','c','d'].map(opt => (
              <input key={opt} placeholder={`${opt.toUpperCase()}) …`} value={q[`option_${opt}`]}
                onChange={e=>update(i,`option_${opt}`,e.target.value)} />
            ))}
          </div>
          <div style={{display:'flex',alignItems:'center',gap:8}}>
            <label style={{margin:0,fontSize:11,textTransform:'none'}}>Correct:</label>
            <select style={{width:70}} value={q.correct_opt} onChange={e=>update(i,'correct_opt',e.target.value)}>
              {['A','B','C','D'].map(o => <option key={o}>{o}</option>)}
            </select>
          </div>
        </div>
      ))}
      <button style={{width:'100%',padding:7,border:'1.5px dashed #cbd5e1',borderRadius:6,background:'none',color:'var(--muted)',cursor:'pointer',fontSize:13}}
              onClick={add}>+ Add Question</button>
    </div>
  )
}

// ─── Create / Edit game form ──────────────────────────────────────────────────

function GameForm({ existing, onDone }) {
  const isEdit  = !!existing?.id
  const toast   = useToast()
  const doCreate = useCreateGame()
  const doUpdate = useUpdateGame(existing?.id)

  const [type,      setType]      = useState(existing?.game_type || 'price_prediction')
  const [title,     setTitle]     = useState(existing?.title || '')
  const [desc,      setDesc]      = useState(existing?.description || '')
  const [symbol,    setSymbol]    = useState(existing?.symbol || 'NIFTY50')
  const [startTime, setStartTime] = useState(utcToLocalInput(existing?.start_time || ''))
  const [endTime,   setEndTime]   = useState(utcToLocalInput(existing?.end_time || ''))
  const [pool,      setPool]      = useState(String(existing?.reward_pool ?? 100))
  const [winners,   setWinners]   = useState(String(existing?.winner_count ?? 3))
  const [cash,      setCash]      = useState(String(existing?.initial_cash ?? 1000000))
  const [questions, setQuestions] = useState(existing?.questions || [])

  async function submit() {
    if (!title.trim()) { toast('Title required', 'err'); return }
    if (!startTime)    { toast('Start time required', 'err'); return }
    if (!endTime)      { toast('End time required', 'err'); return }
    const payload = {
      title:        title.trim(),
      description:  desc.trim(),
      game_type:    type,
      symbol:       type !== 'mcq' ? symbol : null,
      start_time:   localInputToUtc(startTime),
      end_time:     localInputToUtc(endTime),
      reward_pool:  parseInt(pool) || 0,
      winner_count: parseInt(winners) || 1,
      initial_cash: parseInt(cash) || 1000000,
      questions:    type === 'mcq' ? questions : undefined,
    }
    const res = isEdit
      ? await doUpdate.mutateAsync(payload)
      : await doCreate.mutateAsync(payload)
    if (res.ok) { toast(isEdit ? 'Game updated ✓' : 'Game created ✓', 'ok'); onDone(res.id ?? existing?.id) }
    else toast(res.error || 'Failed', 'err')
  }

  const isPending = doCreate.isPending || doUpdate.isPending

  return (
    <div className="game-detail-card">
      <h2 style={{fontSize:15,fontWeight:700,marginBottom:16}}>{isEdit ? 'Edit Game' : 'New Game'}</h2>

      <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8}}>Game Type</div>
      {isEdit ? (
        <div style={{display:'flex',gap:8,alignItems:'center',marginBottom:14}}>
          <span className={`game-type-badge ${TYPE_CLASS[type]||''}`} style={{fontSize:12,padding:'4px 12px'}}>{TYPE_LABEL[type]||type}</span>
          <span style={{fontSize:11,color:'#94a3b8'}}>Game type cannot be changed after creation</span>
        </div>
      ) : (
        <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:14}}>
          {[{v:'price_prediction',icon:'🔮',name:'Price Prediction',desc:'Guess the closing price'},
            {v:'mcq',icon:'📝',name:'Quiz (MCQ)',desc:'Multiple choice questions'},
            {v:'leaderboard',icon:'📈',name:'Trading Challenge',desc:'Virtual portfolio battle'},
          ].map(t => (
            <div key={t.v} onClick={() => setType(t.v)}
              style={{flex:'1 1 100px',minWidth:90,border:`2px solid ${type===t.v?'var(--blue)':'var(--border)'}`,
                borderRadius:8,padding:'10px 8px',cursor:'pointer',background:type===t.v?'#eff6ff':'#fff',
                textAlign:'center',transition:'all .15s'}}>
              <div style={{fontSize:20,marginBottom:4}}>{t.icon}</div>
              <div style={{fontSize:12,fontWeight:700,color:type===t.v?'var(--blue)':'#1e293b'}}>{t.name}</div>
              <div style={{fontSize:10,color:'var(--muted)',marginTop:2}}>{t.desc}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8,marginTop:4}}>Details</div>
      <div className="form-row"><label>Title</label>
        <input placeholder="e.g. Where will Nifty close today?" value={title} onChange={e=>setTitle(e.target.value)} /></div>
      <div className="form-row"><label>Description <span style={{fontWeight:400,textTransform:'none',fontSize:10}}>(optional)</span></label>
        <input placeholder="Brief context for participants" value={desc} onChange={e=>setDesc(e.target.value)} /></div>
      {type !== 'mcq' && (
        <div className="form-row"><label>Symbol</label>
          <select value={symbol} onChange={e=>setSymbol(e.target.value)}>
            {SYMBOLS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
      )}

      <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8,marginTop:4}}>
        Schedule <span style={{fontWeight:400,textTransform:'none',fontSize:10}}>(your local time)</span>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
        <div className="form-row"><label>Opens at</label>
          <input type="datetime-local" value={startTime} onChange={e=>setStartTime(e.target.value)} /></div>
        <div className="form-row"><label>Closes at</label>
          <input type="datetime-local" value={endTime} onChange={e=>setEndTime(e.target.value)} /></div>
      </div>

      <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8,marginTop:4}}>Rewards</div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
        <div className="form-row"><label>Credit Pool</label>
          <input type="number" min="0" value={pool} onChange={e=>setPool(e.target.value)} /></div>
        <div className="form-row"><label>Winners</label>
          <input type="number" min="1" value={winners} onChange={e=>setWinners(e.target.value)} /></div>
      </div>
      {type === 'leaderboard' && (
        <div className="form-row"><label>Starting Cash (₹)</label>
          <input type="number" min="10000" value={cash} onChange={e=>setCash(e.target.value)} /></div>
      )}

      {type === 'mcq' && (
        <>
          <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8,marginTop:4}}>Questions</div>
          <QuestionBuilder questions={questions} onChange={setQuestions} />
        </>
      )}

      <div style={{display:'flex',gap:8,marginTop:18}}>
        <button className="btn btn-primary btn-sm" onClick={submit} disabled={isPending}>
          {isEdit ? 'Save Changes' : 'Create Game'}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => onDone(null)}>Cancel</button>
      </div>
    </div>
  )
}

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function Games({ subscribed, initialGameId }) {
  const user     = useAuthStore(s => s.user)
  const isAdmin  = user?.role === 'super_admin' || user?.role === 'admin'
  const isClient = user?.role === 'client'
  const filters  = isAdmin ? ADMIN_FILTERS : CLIENT_FILTERS
  const [filter, setFilter]     = useState(isAdmin ? 'all' : 'active')
  const [selId,  setSelId]      = useState(initialGameId ?? null)
  const [editing, setEditing]   = useState(null)  // null | {} (create) | {id,...} (edit)

  const { data: games = [], isLoading } = useGames()
  const { data: credits } = useQuery({
    queryKey: ['credits'], queryFn: getCredits, enabled: isClient, refetchInterval: 30000
  })

  const visible = filter === 'all' ? games : games.filter(g => g.status === filter)

  function handleFormDone(newId) {
    setEditing(null)
    if (newId) setSelId(newId)
  }

  const hasDetail = selId !== null || editing !== null

  return (
    <div className={`games-layout${hasDetail ? ' has-detail' : ''}`}>
      {/* Sidebar */}
      <div className="games-sidebar">
        <div className="games-sidebar-hdr">
          <h2>🎮 Games</h2>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            {isClient && (
              <span style={{fontSize:12,color:'#fbbf24',fontWeight:700}}>💎 {credits?.balance ?? '—'}</span>
            )}
            {isAdmin && (
              <button className="btn btn-primary btn-sm" onClick={() => { setEditing({}); setSelId(null) }}>+ Create</button>
            )}
          </div>
        </div>

        <div className="games-filter-bar">
          {filters.map(f => (
            <button key={f} className={`btn btn-ghost btn-sm gfilter${filter===f?' active':''}`} onClick={() => setFilter(f)}>
              {FILTER_LABEL[f]}
            </button>
          ))}
        </div>

        <div className="games-list-scroll">
          {isLoading && <div className="games-empty">Loading games…</div>}
          {!isLoading && !visible.length && <div className="games-empty">No games found.</div>}
          {visible.map(g => {
            const entered = g.my_entry
            return (
              <div key={g.id} className={`game-card${selId===g.id?' active':''}`}
                onClick={() => { setSelId(g.id); setEditing(null) }}>
                <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:6}}>
                  <span className={`game-type-badge ${TYPE_CLASS[g.game_type]||''}`}>{TYPE_LABEL[g.game_type]||g.game_type}</span>
                  <span style={{display:'inline-block',width:7,height:7,borderRadius:'50%',background:STATUS_DOT[g.status]||'#94a3b8',flexShrink:0}} />
                  <span style={{fontSize:10,color:'#94a3b8',fontWeight:600,textTransform:'uppercase'}}>{g.status}</span>
                </div>
                <div style={{fontSize:13,fontWeight:600,color:'#1e293b',marginBottom:6,lineHeight:1.3}}>{g.title}</div>
                <div style={{fontSize:11,color:'#64748b',display:'flex',gap:10,flexWrap:'wrap',marginBottom:entered?6:0}}>
                  <span>💎 {g.reward_pool} · Top {g.winner_count}</span>
                  <span>👥 {g.participant_count}</span>
                  {g.end_time && <span>Ends {fmtIst(g.end_time)}</span>}
                </div>
                {entered && (
                  <div style={{display:'flex',gap:6,alignItems:'center',flexWrap:'wrap'}}>
                    <span className="entered-badge">✓ Entered</span>
                    {entered.rank > 0        && <span style={{fontSize:10,color:'#d97706',fontWeight:700}}>Rank #{entered.rank}</span>}
                    {entered.credits_won > 0 && <span style={{fontSize:10,color:'#fbbf24',fontWeight:700}}>💎 {entered.credits_won} won</span>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Main panel */}
      <div className="games-main">
        <button className="games-back-btn" onClick={() => { setSelId(null); setEditing(null) }}>← Back to games</button>
        {editing !== null
          ? <GameForm existing={editing?.id ? editing : null} onDone={handleFormDone} />
          : selId
            ? <GameDetail id={selId} onEdit={g => setEditing(g)} />
            : <div className="games-empty">Select a game from the list</div>
        }
      </div>
    </div>
  )
}
