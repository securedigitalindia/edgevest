import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useToast } from '../../components/common/Toast'
import { useUsers, useSaveUserProfile } from '../../hooks/useSettings'
import PageHeader from '../../components/common/PageHeader'
import './Profile.css'

function UserRow({ u, isSuperAdmin }) {
  const [open,   setOpen]   = useState(false)
  const [mobile, setMobile] = useState(u.mobile || '')
  const [note,   setNote]   = useState(u.note   || '')
  const [role,   setRole]   = useState(u.role)
  const save  = useSaveUserProfile()
  const toast = useToast()

  async function handleSave() {
    const res = await save.mutateAsync({ uid: u.id, mobile, note, role })
    if (res.ok) { toast('Saved ✓', 'ok'); setOpen(false) }
    else toast(res.error || 'Failed', 'err')
  }

  const prof = u.profile || {}
  const sub  = u.subscription

  const subBadge = sub
    ? <span style={{fontSize:10,fontWeight:700,padding:'2px 7px',borderRadius:10,background:'#dcfce7',color:'#166534'}}>{sub.plan_name} · {sub.end_date}</span>
    : u.role === 'client'
      ? <span style={{fontSize:10,fontWeight:700,padding:'2px 7px',borderRadius:10,background:'#fef2f2',color:'#dc2626'}}>No active plan</span>
      : null

  const profileChips = [
    ...(prof.segment ? prof.segment.split(',') : []),
    prof.risk_type, prof.trader_type, prof.focus?.replace('_',' ')
  ].filter(Boolean).map((v, i) => (
    <span key={i} style={{fontSize:10,background:'#f1f5f9',color:'#334155',padding:'2px 7px',borderRadius:10,fontWeight:600}}>{v}</span>
  ))

  return (
    <div style={{padding:'9px 0',borderBottom:'1px solid #f1f5f9'}}>
      <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:4}}>
        {u.picture
          ? <img src={u.picture} style={{width:26,height:26,borderRadius:'50%',objectFit:'cover',flexShrink:0}} alt="" />
          : <div style={{width:26,height:26,borderRadius:'50%',background:'#3b82f6',display:'flex',alignItems:'center',justifyContent:'center',fontSize:11,fontWeight:700,color:'#fff',flexShrink:0}}>{u.name?.[0]?.toUpperCase()}</div>
        }
        <div style={{flex:1,minWidth:0}}>
          <div style={{display:'flex',alignItems:'center',gap:6,flexWrap:'wrap'}}>
            <span style={{fontSize:13,fontWeight:600,color:'#1e293b'}}>{u.name}</span>
            <span style={{fontSize:11,color:'var(--muted)'}}>{u.email}</span>
            <span style={{fontSize:10,padding:'1px 6px',borderRadius:10,fontWeight:700,
              background:u.role==='super_admin'?'#7c3aed':u.role==='admin'?'#1d4ed8':'#0369a1',color:'#fff'}}>
              {u.role.replace('_',' ')}
            </span>
            {!u.active && <span style={{fontSize:10,background:'#fef2f2',color:'#dc2626',padding:'1px 6px',borderRadius:10,fontWeight:700}}>Inactive</span>}
          </div>
          {(u.mobile || u.note) && <div style={{fontSize:11,color:'var(--muted)',marginTop:2}}>{[u.mobile,u.note].filter(Boolean).join(' · ')}</div>}
        </div>
        <button className="btn btn-ghost btn-sm" style={{flexShrink:0,fontSize:11}} onClick={() => setOpen(v => !v)}>Edit</button>
      </div>

      {subBadge && <div style={{marginBottom:4}}>{subBadge}</div>}

      {profileChips.length > 0
        ? <div style={{display:'flex',gap:4,flexWrap:'wrap',marginBottom:4}}>{profileChips}</div>
        : u.role === 'client' && !prof.setup_done
          ? <div style={{fontSize:11,color:'#94a3b8',marginBottom:4}}>Profile not set up</div>
          : null
      }

      {u.accounts?.length > 0 && (
        <div style={{display:'flex',flexWrap:'wrap',gap:4,marginBottom:4}}>
          {u.accounts.map(a => (
            <span key={a.id} style={{fontSize:11,background:'#f8fafc',border:'1px solid #e2e8f0',padding:'2px 8px',borderRadius:10}}>
              {a.label || [a.broker, a.account_no].filter(Boolean).join(' · ')}
            </span>
          ))}
        </div>
      )}

      {open && (
        <div style={{marginTop:8,paddingTop:8,borderTop:'1px solid #f1f5f9'}}>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:8}}>
            <div className="form-row"><label>Mobile</label>
              <input value={mobile} onChange={e=>setMobile(e.target.value)} placeholder="+91 …" /></div>
            <div className="form-row"><label>Note</label>
              <input value={note} onChange={e=>setNote(e.target.value)} placeholder="Optional" /></div>
          </div>
          {isSuperAdmin && (
            <div className="form-row" style={{marginBottom:8}}><label>Role</label>
              <select value={role} onChange={e=>setRole(e.target.value)}>
                <option value="client">Client</option>
                <option value="admin">Admin</option>
                <option value="super_admin">Super Admin</option>
              </select>
            </div>
          )}
          <div style={{display:'flex',gap:6}}>
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={save.isPending}>Save</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Users() {
  const user          = useAuthStore(s => s.user)
  const isAdmin       = user?.role === 'super_admin' || user?.role === 'admin'
  const isSuperAdmin  = user?.role === 'super_admin'
  const { data: users = [], isLoading } = useUsers()

  if (!isAdmin) return <Navigate to="/profile" replace />

  return (
    <div className="profile-page">
      <PageHeader title="Users" fallback="/profile" />
      <div className="stab-panel active">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !users.length && <div className="empty">No users found.</div>}
        {users.map(u => <UserRow key={u.id} u={u} isSuperAdmin={isSuperAdmin} />)}
      </div>
    </div>
  )
}
