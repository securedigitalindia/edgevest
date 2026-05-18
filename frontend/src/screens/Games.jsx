import { useState } from 'react'
import { useGames, useGame } from '../hooks/useGames'
import useAuthStore from '../store/authStore'
import './Games.css'

const STATUS_DOT = { draft:'#94a3b8', active:'#4ade80', closed:'#f87171', resolved:'#fbbf24' }
const TYPE_LABEL = { price_prediction:'🔮 Prediction', mcq:'📝 Quiz', leaderboard:'📈 Leaderboard' }
const TYPE_CLASS = { price_prediction:'gtype-prediction', mcq:'gtype-mcq', leaderboard:'gtype-leaderboard' }

const CLIENT_FILTERS = ['active','closed','resolved']
const ADMIN_FILTERS  = ['all','draft','active','closed','resolved']
const FILTER_LABEL   = { all:'All', draft:'Draft', active:'Live', closed:'Closed', resolved:'Resolved' }

export default function Games() {
  const user     = useAuthStore(s => s.user)
  const isAdmin  = user?.role === 'super_admin' || user?.role === 'admin'
  const filters  = isAdmin ? ADMIN_FILTERS : CLIENT_FILTERS
  const [filter, setFilter] = useState(isAdmin ? 'all' : 'active')
  const [selId,  setSelId]  = useState(null)

  const { data: games = [], isLoading } = useGames()

  const visible = filter === 'all' ? games : games.filter(g => g.status === filter)

  return (
    <div className="games-layout">
      {/* Sidebar */}
      <div className="games-sidebar">
        <div className="games-sidebar-hdr">
          <h2>🎮 Games</h2>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            {user?.role === 'client' && (
              <span style={{fontSize:12,color:'#fbbf24',fontWeight:700}}>💎 —</span>
            )}
            {isAdmin && (
              <button className="btn btn-primary btn-sm">+ Create</button>
            )}
          </div>
        </div>

        {/* Filter bar */}
        <div className="games-filter-bar">
          {filters.map(f => (
            <button
              key={f}
              className={`btn btn-ghost btn-sm gfilter${filter===f?' active':''}`}
              onClick={() => setFilter(f)}
            >
              {FILTER_LABEL[f]}
            </button>
          ))}
        </div>

        {/* Game list */}
        <div className="games-list-scroll">
          {isLoading && <div className="games-empty">Loading games…</div>}
          {!isLoading && !visible.length && <div className="games-empty">No games found.</div>}
          {visible.map(g => (
            <div
              key={g.id}
              className={`game-card${selId===g.id?' active':''}`}
              onClick={() => setSelId(g.id)}
            >
              <div className="game-card-top">
                <span className={`game-type-badge ${TYPE_CLASS[g.game_type]||''}`}>{TYPE_LABEL[g.game_type]||g.game_type}</span>
                <div className="game-status-dot" style={{background:STATUS_DOT[g.status]||'#94a3b8'}} />
                <h3>{g.title}</h3>
              </div>
              <div className="game-card-meta">
                <span>{g.status.toUpperCase()}</span>
                {g.symbol && <span>{g.symbol}</span>}
                {g.reward_pool > 0 && <span>💎 {g.reward_pool}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Main panel */}
      <div className="games-main">
        {selId
          ? <GameDetail id={selId} user={user} isAdmin={isAdmin} />
          : <div className="games-empty">Select a game from the list</div>
        }
      </div>
    </div>
  )
}

function GameDetail({ id, user, isAdmin }) {
  const { data: game, isLoading } = useGame(id)

  if (isLoading) return <div className="games-empty">Loading…</div>
  if (!game)     return <div className="games-empty">Game not found.</div>

  return (
    <div className="game-detail-card">
      <div className="game-detail-hdr">
        <h2>{game.title}</h2>
        <span className="game-status-dot" style={{background:STATUS_DOT[game.status]||'#94a3b8',width:10,height:10,borderRadius:'50%',display:'inline-block'}} />
      </div>
      {game.description && <p className="game-detail-desc">{game.description}</p>}
      <div className="empty" style={{marginTop:32}}>
        Full game interaction UI coming soon.
      </div>
    </div>
  )
}
