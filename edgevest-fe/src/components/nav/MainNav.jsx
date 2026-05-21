import { useState, useRef, useEffect } from 'react'
import useAuthStore from '../../store/authStore'
import { useQuery } from '@tanstack/react-query'
import { getCredits } from '../../api/games'
import './MainNav.css'

export default function MainNav({ activeTab, onTabChange, onOpenDrawer }) {
  const user     = useAuthStore(s => s.user)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef  = useRef(null)
  const isClient = user?.role === 'client'
  const isAdmin  = user?.role === 'super_admin' || user?.role === 'admin'

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
    <nav className="main-nav">
      <div className="nav-brand">
        <span className="nav-brand-icon">📊</span>
        <span className="nav-brand-name">Drishti</span>
      </div>
      <div className="nav-tabs">
        <button className={`main-nav-tab${activeTab==='dashboard'?' active':''}`} onClick={()=>onTabChange('dashboard')}>Dashboard</button>
        <button className={`main-nav-tab${activeTab==='games'?' active':''}`} onClick={()=>onTabChange('games')}>Games</button>
      </div>
      <div className="nav-right">
        {isClient && (
          <div className="nav-credits-pill" onClick={()=>onTabChange('games')} title="Your credits">
            💎 <span>{credits?.balance ?? '—'}</span>
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
                <span className={`role-chip role-chip-${user.role}`}>{user.role.replace('_',' ').toUpperCase()}</span>
              </div>
              {isClient && <div className="prof-menu-credits">💎 {credits?.balance ?? '—'} credits</div>}
              <div className="prof-menu-item" style={{cursor:'pointer'}} onClick={() => { setMenuOpen(false); onOpenDrawer('profile') }}>Profile</div>
              <div style={{height:1,background:'#2d3f55',margin:'2px 0'}} />
              <a href="/logout" className="prof-menu-item">Sign out</a>
            </div>
          )}
        </div>
        <button className="hdr-btn" onClick={()=>{ setMenuOpen(false); onOpenDrawer() }} title="Settings">⚙</button>
      </div>
    </nav>
  )
}
