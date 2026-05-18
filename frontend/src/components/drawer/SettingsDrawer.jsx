import { useState, useEffect } from 'react'
import useAuthStore from '../../store/authStore'
import api from '../../api/client'
import { useToast } from '../common/Toast'
import { useBrokers, useAddBroker, useAccounts, useAddAccount } from '../../hooks/useTrades'
import { useUsers, useSaveUserProfile, usePlans, useCreatePlan, useTogglePlan, useSubs } from '../../hooks/useSettings'
import './SettingsDrawer.css'

export default function SettingsDrawer({ open, onClose, initialTab }) {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const isSuperAdmin = user?.role === 'super_admin'
  const defaultTab = isAdmin ? 'brokers' : 'accounts'
  const [tab, setTab]     = useState(defaultTab)

  useEffect(() => {
    if (open && initialTab) setTab(initialTab)
    else if (open && !initialTab) setTab(defaultTab)
  }, [open, initialTab])
  const [mobile, setMobile] = useState(user?.mobile || '')
  const toast = useToast()

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
            {isAdmin ? <>
              <button className={`stab${tab==='brokers'?' active':''}`}  onClick={()=>setTab('brokers')}>Brokers</button>
              <button className={`stab${tab==='users'?' active':''}`}    onClick={()=>setTab('users')}>Users</button>
              <button className={`stab${tab==='plans'?' active':''}`}    onClick={()=>setTab('plans')}>Plans</button>
              <button className={`stab${tab==='subs'?' active':''}`}     onClick={()=>setTab('subs')}>Subscriptions</button>
            </> : (
              <button className={`stab${tab==='accounts'?' active':''}`} onClick={()=>setTab('accounts')}>My Accounts</button>
            )}
            <button className={`stab${tab==='profile'?' active':''}`}   onClick={()=>setTab('profile')}>Profile</button>
          </div>

          {tab === 'profile' && (
            <ProfileTab user={user} mobile={mobile} setMobile={setMobile} onSave={saveProfile} />
          )}
          {tab === 'accounts' && <AccountsTab />}
          {tab === 'brokers'  && <BrokersTab />}
          {tab === 'users'    && <UsersTab isSuperAdmin={isSuperAdmin} />}
          {tab === 'plans'    && <PlansTab />}
          {tab === 'subs'     && <SubsTab />}
        </div>
      </div>
    </>
  )
}

// ─── Profile ─────────────────────────────────────────────────────────────────

function ProfileTab({ user, mobile, setMobile, onSave }) {
  return (
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
      <button className="btn btn-primary btn-sm" onClick={onSave}>Save changes</button>
    </div>
  )
}

// ─── My Accounts (client) ─────────────────────────────────────────────────────

function AccountsTab() {
  const { data: accounts = [], isLoading } = useAccounts()
  const { data: brokers  = [] }            = useBrokers()
  const addAccount = useAddAccount()
  const toast      = useToast()
  const [brokerId, setBrokerId] = useState('')
  const [acctNo,   setAcctNo]   = useState('')
  const [label,    setLabel]    = useState('')

  async function add() {
    if (!brokerId) { toast('Select a broker', 'err'); return }
    const res = await addAccount.mutateAsync({ broker_id: parseInt(brokerId), account_no: acctNo, label })
    if (res.ok) { toast('Account added ✓', 'ok'); setBrokerId(''); setAcctNo(''); setLabel('') }
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="stab-panel active">
      <div className="settings-list">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !accounts.length && <div className="empty">No accounts yet. Add one below.</div>}
        {accounts.map(a => (
          <div key={a.id} style={{display:'flex',alignItems:'center',gap:8,padding:'7px 0',borderBottom:'1px solid #f1f5f9'}}>
            <div style={{flex:1}}>
              <div style={{fontWeight:600,fontSize:13}}>{a.label || [a.broker, a.account_no].filter(Boolean).join(' · ')}</div>
              {(a.broker || a.account_no) && <div style={{fontSize:11,color:'var(--muted)'}}>{[a.broker, a.account_no].filter(Boolean).join('  ·  ')}</div>}
            </div>
          </div>
        ))}
      </div>
      <div style={{background:'#f8fafc',border:'1px solid var(--border)',borderRadius:8,padding:12,marginTop:4}}>
        <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:10}}>Add Account</div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
          <div className="form-row">
            <label>Broker</label>
            <select value={brokerId} onChange={e=>setBrokerId(e.target.value)}>
              <option value="">Select…</option>
              {brokers.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div className="form-row">
            <label>Account No.</label>
            <input placeholder="Broker account ID" value={acctNo} onChange={e=>setAcctNo(e.target.value)} />
          </div>
        </div>
        <div className="form-row">
          <label>Label (optional)</label>
          <input placeholder="e.g. Zerodha Main" value={label} onChange={e=>setLabel(e.target.value)} />
        </div>
        <button className="btn btn-primary btn-sm" onClick={add} disabled={addAccount.isPending}>Add Account</button>
      </div>
    </div>
  )
}

// ─── Brokers (admin) ─────────────────────────────────────────────────────────

function BrokersTab() {
  const { data: brokers = [], isLoading } = useBrokers()
  const addBroker = useAddBroker()
  const toast     = useToast()
  const [name, setName] = useState('')

  async function add() {
    if (!name.trim()) { toast('Enter broker name', 'err'); return }
    const res = await addBroker.mutateAsync({ name: name.trim() })
    if (res.ok) { toast('Broker added ✓', 'ok'); setName('') }
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="stab-panel active">
      <div className="settings-list">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !brokers.length && <div style={{color:'var(--muted)',fontSize:13,padding:'8px 0'}}>No brokers yet.</div>}
        {brokers.map(b => (
          <div key={b.id} className="settings-item">
            <div className="s-name">{b.name}</div>
            <div className="s-meta">id: {b.id}</div>
          </div>
        ))}
      </div>
      <div style={{background:'#f8fafc',border:'1px solid var(--border)',borderRadius:8,padding:12}}>
        <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:10}}>Add Broker</div>
        <div className="form-row">
          <label>Name</label>
          <input placeholder="e.g. Upstox, Zerodha" value={name} onChange={e=>setName(e.target.value)} />
        </div>
        <button className="btn btn-primary btn-sm" onClick={add} disabled={addBroker.isPending}>Add</button>
      </div>
    </div>
  )
}

// ─── Users (admin) ───────────────────────────────────────────────────────────

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

function UsersTab({ isSuperAdmin }) {
  const { data: users = [], isLoading } = useUsers()
  return (
    <div className="stab-panel active">
      {isLoading && <div className="empty">Loading…</div>}
      {!isLoading && !users.length && <div className="empty">No users found.</div>}
      {users.map(u => <UserRow key={u.id} u={u} isSuperAdmin={isSuperAdmin} />)}
    </div>
  )
}

// ─── Plans (admin) ───────────────────────────────────────────────────────────

function PlansTab() {
  const { data: plans = [], isLoading } = usePlans()
  const createPlan = useCreatePlan()
  const togglePlan = useTogglePlan()
  const toast      = useToast()
  const [name,     setName]     = useState('')
  const [price,    setPrice]    = useState('0')
  const [duration, setDuration] = useState('30')
  const [desc,     setDesc]     = useState('')

  async function create() {
    if (!name.trim()) { toast('Enter plan name', 'err'); return }
    const res = await createPlan.mutateAsync({ name: name.trim(), description: desc, price: parseInt(price||0), duration_days: parseInt(duration||30) })
    if (res.ok) { toast('Plan created ✓', 'ok'); setName(''); setPrice('0'); setDuration('30'); setDesc('') }
    else toast(res.error || 'Failed', 'err')
  }

  async function toggle(id, active) {
    const res = await togglePlan.mutateAsync({ id, active: !active })
    if (res.ok) toast(`Plan ${active ? 'disabled' : 'enabled'} ✓`, 'ok')
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="stab-panel active">
      <div className="settings-list">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !plans.length && <div style={{color:'var(--muted)',fontSize:13,padding:'8px 0'}}>No plans yet.</div>}
        {plans.map(p => (
          <div key={p.id} style={{display:'flex',alignItems:'center',gap:10,padding:'9px 0',borderBottom:'1px solid #f1f5f9'}}>
            <div style={{flex:1}}>
              <div style={{display:'flex',alignItems:'center',gap:6,flexWrap:'wrap'}}>
                <span style={{fontSize:13,fontWeight:600}}>{p.name}</span>
                {p.price === 0 && <span style={{fontSize:10,background:'#dcfce7',color:'#166534',padding:'1px 6px',borderRadius:10,fontWeight:700}}>Free</span>}
                {!p.active && <span style={{fontSize:10,background:'#f1f5f9',color:'#94a3b8',padding:'1px 6px',borderRadius:10,fontWeight:700}}>Inactive</span>}
              </div>
              <div style={{fontSize:11,color:'var(--muted)'}}>₹{p.price} · {p.duration_days} days{p.description?` · ${p.description}`:''}</div>
            </div>
            <button className={`btn btn-sm ${p.active ? 'btn-ghost' : 'btn-success'}`}
                    style={p.active?{color:'var(--red)',borderColor:'#fca5a5',fontSize:11}:{fontSize:11}}
                    onClick={() => toggle(p.id, p.active)}>
              {p.active ? 'Deactivate' : 'Activate'}
            </button>
          </div>
        ))}
      </div>
      <div style={{background:'#f8fafc',border:'1px solid var(--border)',borderRadius:8,padding:12,marginTop:4}}>
        <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:10}}>New Plan</div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
          <div className="form-row">
            <label>Name</label>
            <input placeholder="e.g. Pro Monthly" value={name} onChange={e=>setName(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Price (₹)</label>
            <input type="number" min="0" value={price} onChange={e=>setPrice(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Duration (days)</label>
            <input type="number" min="1" value={duration} onChange={e=>setDuration(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Description</label>
            <input placeholder="Short description" value={desc} onChange={e=>setDesc(e.target.value)} />
          </div>
        </div>
        <button className="btn btn-primary btn-sm" onClick={create} disabled={createPlan.isPending}>Create Plan</button>
      </div>
    </div>
  )
}

// ─── Subscriptions (admin) ───────────────────────────────────────────────────

function SubsTab() {
  const { data: subs = [], isLoading } = useSubs()

  return (
    <div className="stab-panel active">
      {isLoading && <div className="empty">Loading…</div>}
      {!isLoading && !subs.length && <div className="empty">No subscriptions.</div>}
      {subs.map(s => (
        <div key={s.id} style={{padding:'9px 0',borderBottom:'1px solid #f1f5f9'}}>
          <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:3}}>
            <span style={{fontSize:13,fontWeight:600,flex:1}}>{s.user_name}</span>
            <span style={{fontSize:11,padding:'2px 7px',borderRadius:20,fontWeight:600,
                          background:s.status==='active'?'#dcfce7':'#f1f5f9',
                          color:s.status==='active'?'#166534':'#64748b'}}>
              {s.status}
            </span>
          </div>
          <div style={{fontSize:11,color:'var(--muted)',display:'flex',gap:10,flexWrap:'wrap'}}>
            <span>{s.email}</span>
            <span>{s.plan_name}</span>
            <span>{s.start_date} → {s.end_date}</span>
            {s.amount_paid > 0 && <span>₹{s.amount_paid}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}
