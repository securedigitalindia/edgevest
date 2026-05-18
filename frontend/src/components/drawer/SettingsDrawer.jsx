import { useState } from 'react'
import useAuthStore from '../../store/authStore'
import api from '../../api/client'
import { useToast } from '../common/Toast'
import './SettingsDrawer.css'

export default function SettingsDrawer({ open, onClose }) {
  const user    = useAuthStore(s => s.user)
  const toast   = useToast()
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const defaultTab = isAdmin ? 'brokers' : 'accounts'
  const [tab, setTab]     = useState(defaultTab)
  const [mobile, setMobile] = useState(user?.mobile || '')

  if (!user) return null

  async function saveProfile() {
    const res = await api.post(`/users/${user.id}/profile`, { mobile })
    if (res.data.ok) toast('Profile saved', 'ok')
    else toast(res.data.error || 'Error', 'err')
  }

  return (
    <>
      <div className={`drawer-overlay${open?' open':''}`} onClick={onClose} />
      <div className={`drawer${open?' open':''}`}>
        <div className="drawer-header">
          <h2>Settings</h2>
          <button className="drawer-close" onClick={onClose}>✕</button>
        </div>
        <div className="drawer-body">
          <div className="stabs">
            {isAdmin ? (
              <>
                <button className={`stab${tab==='brokers'?' active':''}`} onClick={()=>setTab('brokers')}>Brokers</button>
                <button className={`stab${tab==='users'?' active':''}`} onClick={()=>setTab('users')}>Users</button>
                <button className={`stab${tab==='plans'?' active':''}`} onClick={()=>setTab('plans')}>Plans</button>
                <button className={`stab${tab==='subs'?' active':''}`} onClick={()=>setTab('subs')}>Subscriptions</button>
              </>
            ) : (
              <button className={`stab${tab==='accounts'?' active':''}`} onClick={()=>setTab('accounts')}>My Accounts</button>
            )}
            <button className={`stab${tab==='profile'?' active':''}`} onClick={()=>setTab('profile')}>Profile</button>
          </div>

          {tab === 'profile' && (
            <div className="stab-panel active">
              <div style={{display:'flex',flexDirection:'column',alignItems:'center',padding:'20px 0 18px',gap:8}}>
                {user.picture
                  ? <img src={user.picture} style={{width:68,height:68,borderRadius:'50%',objectFit:'cover',border:'2px solid #e2e8f0'}} alt="" />
                  : <div style={{width:68,height:68,borderRadius:'50%',background:'#3b82f6',display:'flex',alignItems:'center',justifyContent:'center',fontSize:26,fontWeight:700,color:'#fff'}}>{user.name[0].toUpperCase()}</div>
                }
                <div style={{fontSize:16,fontWeight:700,color:'#1e293b',marginTop:4}}>{user.name}</div>
                <span className={`role-chip role-chip-${user.role}`}>{user.role.replace('_',' ').toUpperCase()}</span>
              </div>
              <div className="settings-list">
                <div className="settings-item">
                  <div className="s-name">Email</div>
                  <div className="s-meta" style={{marginTop:2,wordBreak:'break-all'}}>{user.email}</div>
                </div>
                <div className="settings-item" style={{paddingBottom:12}}>
                  <label>Mobile</label>
                  <input placeholder="+91 98765 43210" value={mobile} onChange={e=>setMobile(e.target.value)} />
                </div>
              </div>
              <button className="btn btn-primary btn-sm" onClick={saveProfile}>Save changes</button>
            </div>
          )}

          {tab === 'accounts' && (
            <div className="stab-panel active">
              <div className="empty">Account management coming soon.</div>
            </div>
          )}

          {isAdmin && tab !== 'profile' && (
            <div className="stab-panel active">
              <div className="empty">{tab.charAt(0).toUpperCase()+tab.slice(1)} management coming soon.</div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
