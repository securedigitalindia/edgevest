import { useState, useRef, useEffect } from 'react'
import { authUrl } from '../../api/client'
import { useLocation, useNavigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useQuery } from '@tanstack/react-query'
import { getCredits } from '../../api/games'
import { DashboardIcon, PositionsIcon, GameIcon, ProfileIcon, GemIcon } from '../common/Icons'
import './MainNav.css'

export default function MainNav({ subscribed }) {
  const user      = useAuthStore(s => s.user)
  const location  = useLocation()
  const navigate  = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef   = useRef(null)
  const isClient  = user?.role === 'client'
  const activeTab = location.pathname.startsWith('/games')     ? 'games' :
                    location.pathname.startsWith('/positions') ? 'positions' :
                    location.pathname.startsWith('/profile')   ? 'profile' :
                    'dashboard'

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
          <span className="nav-brand-icon">📊</span>
          <span className="nav-brand-name">EdgeVest</span>
        </div>
        <div className="nav-tabs">
          <button className={`main-nav-tab${activeTab==='dashboard'?' active':''}`} onClick={() => navigate('/dashboard', {replace:true})}>Dashboard</button>
          <button className={`main-nav-tab${activeTab==='positions'?' active':''}`} onClick={() => navigate('/positions', {replace:true})}>Positions</button>
          <button className={`main-nav-tab${activeTab==='games'?' active':''}`} onClick={() => navigate('/games', {replace:true})}>Games</button>
          <button className={`main-nav-tab${activeTab==='profile'?' active':''}`} onClick={() => navigate('/profile', {replace:true})}>Profile</button>
        </div>
        <div className="nav-right">
          {isClient && (
            <div className="nav-credits-pill" onClick={() => navigate('/games', {replace:true})} title="Your credits">
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
                <div className="prof-menu-item" style={{cursor:'pointer'}} onClick={() => { setMenuOpen(false); navigate('/profile', {replace:true}) }}>Profile</div>
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
        <button className={`bottom-nav-tab${activeTab==='dashboard'?' active':''}`} onClick={() => navigate('/dashboard', {replace:true})}>
          <span className="bottom-nav-tab-icon"><DashboardIcon /></span>
          Dashboard
        </button>
        <button className={`bottom-nav-tab${activeTab==='positions'?' active':''}`} onClick={() => navigate('/positions', {replace:true})}>
          <span className="bottom-nav-tab-icon"><PositionsIcon /></span>
          Positions
        </button>
        <button className={`bottom-nav-tab${activeTab==='games'?' active':''}`} onClick={() => navigate('/games', {replace:true})}>
          <span className="bottom-nav-tab-icon"><GameIcon size={20} /></span>
          Games
        </button>
        <button className={`bottom-nav-tab${activeTab==='profile'?' active':''}`} onClick={() => navigate('/profile', {replace:true})}>
          <span className="bottom-nav-tab-icon"><ProfileIcon /></span>
          Profile
        </button>
      </div>
    </>
  )
}
