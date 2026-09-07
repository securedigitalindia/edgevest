import { useMemo, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useToast } from '../../components/common/Toast'
import { useUsers, useSaveUserProfile } from '../../hooks/useSettings'
import { usePayments } from '../../hooks/useBilling'
import PageHeader from '../../components/common/PageHeader'
import Dropdown from '../../components/common/Dropdown'
import { fmtRs } from '../../utils/format'
import './Profile.css'

function UserRow({ u, isSuperAdmin, totalPaid }) {
  const [open,   setOpen]   = useState(false)
  const [mobile, setMobile] = useState(u.mobile || '')
  const [note,   setNote]   = useState(u.note   || '')
  const [role,   setRole]   = useState(u.role)
  const save     = useSaveUserProfile()
  const toast    = useToast()
  const navigate = useNavigate()

  async function handleSave() {
    const res = await save.mutateAsync({ uid: u.id, mobile, note, role })
    if (res.ok) { toast('Saved ✓', 'ok'); setOpen(false) }
    else toast(res.error || 'Failed', 'err')
  }

  const prof = u.profile || {}
  const sub  = u.subscription

  const profileChips = [
    ...(prof.segment ? prof.segment.split(',') : []),
    prof.risk_type, prof.trader_type, prof.focus?.replace('_',' ')
  ].filter(Boolean).map((v, i) => (
    <span key={i} style={{fontSize:10,background:'#f1f5f9',color:'#334155',padding:'2px 7px',borderRadius:10,fontWeight:600}}>{v}</span>
  ))

  // Single summary line — subscription state and payment total, one clause each,
  // instead of the old stack of separate badges that made every row 3-4 lines tall.
  let summary = null
  if (sub) {
    summary = <span style={{color:'#166534'}}>{sub.plan_name} · ends {sub.end_date}</span>
  } else if (u.role === 'client') {
    summary = <span style={{color:'#dc2626'}}>No active plan</span>
  }

  return (
    <div style={{padding:'10px 0',borderBottom:'1px solid #f1f5f9'}}>
      <div style={{display:'flex',alignItems:'center',gap:8}}>
        {u.picture
          ? <img src={u.picture} style={{width:28,height:28,borderRadius:'50%',objectFit:'cover',flexShrink:0}} alt="" />
          : <div style={{width:28,height:28,borderRadius:'50%',background:'#3b82f6',display:'flex',alignItems:'center',justifyContent:'center',fontSize:11,fontWeight:700,color:'#fff',flexShrink:0}}>{u.name?.[0]?.toUpperCase()}</div>
        }
        <div style={{flex:1,minWidth:0}}>
          <div style={{display:'flex',alignItems:'center',gap:6}}>
            <span style={{fontSize:13,fontWeight:600,color:'#1e293b',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{u.name}</span>
            {u.role !== 'client' && (
              <span style={{fontSize:9,padding:'1px 6px',borderRadius:10,fontWeight:700,flexShrink:0,
                background:u.role==='super_admin'?'#7c3aed':'#1d4ed8',color:'#fff'}}>
                {u.role.replace('_',' ')}
              </span>
            )}
            {!u.active && <span style={{fontSize:9,background:'#fef2f2',color:'#dc2626',padding:'1px 6px',borderRadius:10,fontWeight:700,flexShrink:0}}>Inactive</span>}
          </div>
          <div style={{fontSize:11,color:'var(--muted)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{u.email}</div>
        </div>
        <button className="btn btn-ghost btn-sm" style={{flexShrink:0,fontSize:11}} onClick={() => setOpen(v => !v)}>{open ? 'Close' : 'Edit'}</button>
      </div>

      {(summary || totalPaid > 0) && (
        <div style={{fontSize:11,marginTop:4,paddingLeft:36,display:'flex',gap:6,alignItems:'center'}}>
          {summary}
          {summary && totalPaid > 0 && <span style={{color:'#cbd5e1'}}>·</span>}
          {totalPaid > 0 && (
            <span style={{color:'#1d4ed8',fontWeight:600,cursor:'pointer'}}
              onClick={() => navigate(`/profile/payments?u=${encodeURIComponent(u.email)}`)}>
              {fmtRs(totalPaid)} paid ›
            </span>
          )}
        </div>
      )}

      {open && (
        <div style={{marginTop:10,paddingTop:10,borderTop:'1px solid #f1f5f9'}}>
          {(profileChips.length > 0 || u.accounts?.length > 0) && (
            <div style={{marginBottom:10}}>
              {profileChips.length > 0 && (
                <div style={{display:'flex',flexWrap:'wrap',gap:4,marginBottom:u.accounts?.length ? 6 : 0}}>{profileChips}</div>
              )}
              {u.accounts?.length > 0 && (
                <div style={{display:'flex',flexWrap:'wrap',gap:4}}>
                  {u.accounts.map(a => (
                    <span key={a.id} style={{fontSize:11,background:'#f8fafc',border:'1px solid #e2e8f0',padding:'2px 8px',borderRadius:10}}>
                      {a.label || [a.broker, a.account_no].filter(Boolean).join(' · ')}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          {u.role === 'client' && !prof.setup_done && profileChips.length === 0 && (
            <div style={{fontSize:11,color:'#94a3b8',marginBottom:10}}>Profile not set up</div>
          )}
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:8}}>
            <div className="form-row"><label>Mobile</label>
              <input value={mobile} onChange={e=>setMobile(e.target.value)} placeholder="+91 …" /></div>
            <div className="form-row"><label>Note</label>
              <input value={note} onChange={e=>setNote(e.target.value)} placeholder="Optional" /></div>
          </div>
          {isSuperAdmin && (
            <div className="form-row" style={{marginBottom:8}}><label>Role</label>
              <Dropdown variant="form" value={role} onChange={setRole} options={[
                { value: 'client', label: 'Client' },
                { value: 'admin', label: 'Admin' },
                { value: 'super_admin', label: 'Super Admin' },
              ]} />
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

const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
function monthLabel(m) {
  const [y, mo] = m.split('-').map(Number)
  return `${MONTH_NAMES[mo - 1]} '${String(y).slice(2)}`
}

// Hand-rolled, no charting dependency — same posture as ReportCharts.jsx and
// Subscriptions.jsx's own monthly trend. One series (new_signups) drives the
// bar; cumulative_users rides along as plain text underneath (never
// dual-axis — a running total is a different scale from a monthly count).
function SignupTrend({ data }) {
  if (!data.length) return null
  const max = Math.max(1, ...data.map(d => d.new_signups))
  return (
    <div className="stab-panel active" style={{marginBottom:14}}>
      <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:10}}>
        New Clients — Month on Month
      </div>
      <div style={{display:'flex',alignItems:'flex-end',gap:8,height:76}}>
        {data.map(d => {
          const h = Math.max(4, Math.round((d.new_signups / max) * 60))
          return (
            <div key={d.month} style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'flex-end',gap:4,height:'100%'}}>
              <div style={{fontSize:11,fontWeight:700,color:'#1e293b'}}>{d.new_signups}</div>
              <div
                title={`${d.new_signups} new client${d.new_signups===1?'':'s'} in ${monthLabel(d.month)} · ${d.cumulative_users} total clients by month end`}
                style={{width:'100%',maxWidth:30,height:h,background:'#0369a1',borderRadius:'4px 4px 2px 2px'}}
              />
            </div>
          )
        })}
      </div>
      <div style={{display:'flex',gap:8,marginTop:8,paddingTop:8,borderTop:'1px solid #f1f5f9'}}>
        {data.map(d => (
          <div key={d.month} style={{flex:1,textAlign:'center',minWidth:0}}>
            <div style={{fontSize:10,fontWeight:700,color:'var(--muted)'}}>{monthLabel(d.month)}</div>
            <div style={{fontSize:9,color:'#94a3b8',marginTop:1,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>
              {d.cumulative_users} total
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Users() {
  const user          = useAuthStore(s => s.user)
  const isAdmin       = user?.role === 'super_admin' || user?.role === 'admin'
  const isSuperAdmin  = user?.role === 'super_admin'
  const { data, isLoading } = useUsers()
  const users          = data?.users ?? []
  const signupTrend    = data?.monthly_signup_trend ?? []
  const { data: payments = [] } = usePayments()

  const paidByUser = useMemo(() => {
    const map = {}
    for (const p of payments) {
      if (p.status !== 'paid') continue
      map[p.user_id] = (map[p.user_id] || 0) + (p.amount || 0)
    }
    return map
  }, [payments])

  if (!isAdmin) return <Navigate to="/profile" replace />

  return (
    <div className="profile-page">
      <PageHeader title="Users" fallback="/profile" />
      <SignupTrend data={signupTrend} />
      <div className="stab-panel active">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !users.length && <div className="empty">No users found.</div>}
        {users.map(u => <UserRow key={u.id} u={u} isSuperAdmin={isSuperAdmin} totalPaid={paidByUser[u.id] || 0} />)}
      </div>
    </div>
  )
}
