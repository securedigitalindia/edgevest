import { useState, useRef, useEffect } from 'react'
import { authUrl } from '../../api/client'
import { useLocation, useNavigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useQuery } from '@tanstack/react-query'
import { getCredits } from '../../api/games'
import { DashboardIcon, ChartIcon, PositionsIcon, GameIcon, ProfileIcon, GemIcon } from '../common/Icons'
import './MainNav.css'

export default function MainNav({ subscribed }) {
  const user      = useAuthStore(s => s.user)
  const location  = useLocation()
  const navigate  = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef   = useRef(null)
  const isClient  = user?.role === 'client'
  const activeTab = location.pathname.startsWith('/games')     ? 'games' :
                    location.pathname.startsWith('/trades')    ? 'trades' :
                    location.pathname.startsWith('/positions') ? 'positions' :
                    location.pathname.startsWith('/profile')   ? 'profile' :
                    'dashboard'
  // Collapse repeated top-level tab clicks into one history entry — but only
  // while already ON a top-level tab route (exact match; a drill-down like
  // /profile/gems doesn't count). Replacing unconditionally (including from
  // a drill-down page) was overwriting whatever page you'd drilled into
  // instead of the stable "current tab" slot, so different click sequences
  // could leave two separate history entries both rendering the same tab —
  // back would then land on a visually-identical page twice in a row.
  // Pushing when leaving a drill-down keeps that page reachable via back.
  const atTopLevel = ['/dashboard', '/trades', '/positions', '/games', '/profile'].includes(location.pathname)

  const { data: credits } = useQuery({
    queryKey: ['credits'],
    queryFn:  getCredits,
    enabled:  isClient,
    refetchInterval: 30000,
  })

  useEffect(() => {
    const close = e => { if (!menuRef.current?.contains(e.target)) setMenuOpen(false) }
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [])

  if (!user) return null

  return (
    <>
      <nav className="main-nav">
        <div className="nav-brand">
          {/* icon-tile-blue from the brand kit (public/brand/), inlined for
              crispness — signal-blue tile reads clearly on the dark navbar,
              where the ink-tile variant would nearly disappear. */}
          <svg className="nav-brand-icon" width="30" height="30" viewBox="0 0 104 104" aria-hidden="true">
            <rect width="104" height="104" rx="26" fill="#1F7FD0"/>
            <g transform="translate(21 21)">
              <rect x="8" y="14" width="7" height="36" rx="3" fill="#0D1520"/>
              <rect x="22" y="30" width="7" height="20" rx="3" fill="rgba(13,21,32,0.45)"/>
              <rect x="36" y="20" width="7" height="30" rx="3" fill="rgba(255,255,255,0.82)"/>
              <rect x="50" y="8" width="7" height="42" rx="3" fill="#ffffff"/>
            </g>
          </svg>
          <span className="nav-brand-name">Edge<span className="nav-brand-name-bold">Vest</span></span>
        </div>
        <div className="nav-tabs">
          <button className={`main-nav-tab${activeTab==='dashboard'?' active':''}`} onClick={() => navigate('/dashboard', {replace: atTopLevel})}>Dashboard</button>
          <button className={`main-nav-tab${activeTab==='trades'?' active':''}`} onClick={() => navigate('/trades', {replace: atTopLevel})}>Trades</button>
          <button className={`main-nav-tab${activeTab==='positions'?' active':''}`} onClick={() => navigate('/positions', {replace: atTopLevel})}>Positions</button>
          <button className={`main-nav-tab${activeTab==='games'?' active':''}`} onClick={() => navigate('/games', {replace: atTopLevel})}>Games</button>
          <button className={`main-nav-tab${activeTab==='profile'?' active':''}`} onClick={() => navigate('/profile', {replace: atTopLevel})}>Profile</button>
        </div>
        <div className="nav-right">
          {isClient && (
            <div className="nav-credits-pill" onClick={() => navigate('/games', {replace: atTopLevel})} title="Your credits">
              <GemIcon size={12}/> <span>{credits?.balance ?? '—'}</span>
            </div>
          )}
          <div className="prof-trigger" ref={menuRef} onClick={e=>{ e.stopPropagation(); setMenuOpen(o=>!o) }}>
            {user.picture
              ? <img src={user.picture} className="prof-avatar" alt="" />
              : <div className="prof-avatar-initials">{user.name[0].toUpperCase()}</div>
            }
            <span className="prof-trigger-name">{user.name.split(' ')[0]}</span>
            <span className="prof-trigger-caret">▾</span>

            {menuOpen && (
              <div className="prof-menu" onClick={e=>e.stopPropagation()}>
                <div className="prof-menu-head">
                  <div className="prof-menu-name">{user.name}</div>
                  {!isClient && <span className={`role-chip role-chip-${user.role}`}>{user.role.replace('_',' ').toUpperCase()}</span>}
                </div>
                {isClient && <div className="prof-menu-credits" style={{display:'flex',alignItems:'center',gap:5}}><GemIcon size={12}/> {credits?.balance ?? '—'} credits</div>}
                <div className="prof-menu-item" style={{cursor:'pointer'}} onClick={() => { setMenuOpen(false); navigate('/profile', {replace: atTopLevel}) }}>Profile</div>
                <div style={{height:1,background:'#2d3f55',margin:'2px 0'}} />
                <div style={{padding:'6px 14px',fontSize:10,color:'#475569',letterSpacing:.3}}>EdgeVest v{__APP_VERSION__}</div>
                <div style={{height:1,background:'#2d3f55',margin:'2px 0'}} />
                <button className="prof-menu-item" onClick={() => window.location.replace(authUrl('/logout'))}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* Bottom tab bar — mobile only */}
      <div className="bottom-nav">
        <button className={`bottom-nav-tab${activeTab==='dashboard'?' active':''}`} onClick={() => navigate('/dashboard', {replace: atTopLevel})}>
          <span className="bottom-nav-tab-icon"><DashboardIcon /></span>
          Dashboard
        </button>
        <button className={`bottom-nav-tab${activeTab==='trades'?' active':''}`} onClick={() => navigate('/trades', {replace: atTopLevel})}>
          <span className="bottom-nav-tab-icon"><ChartIcon size={20} /></span>
          Trades
        </button>
        <button className={`bottom-nav-tab${activeTab==='positions'?' active':''}`} onClick={() => navigate('/positions', {replace: atTopLevel})}>
          <span className="bottom-nav-tab-icon"><PositionsIcon /></span>
          Positions
        </button>
        <button className={`bottom-nav-tab${activeTab==='games'?' active':''}`} onClick={() => navigate('/games', {replace: atTopLevel})}>
          <span className="bottom-nav-tab-icon"><GameIcon size={20} /></span>
          Games
        </button>
        <button className={`bottom-nav-tab${activeTab==='profile'?' active':''}`} onClick={() => navigate('/profile', {replace: atTopLevel})}>
          <span className="bottom-nav-tab-icon"><ProfileIcon /></span>
          Profile
        </button>
      </div>
    </>
  )
}
