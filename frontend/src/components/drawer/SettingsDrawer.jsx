import { useState, useEffect } from 'react'
import { AUTH_BASE } from '../../api/client'
import { useQuery } from '@tanstack/react-query'
import useAuthStore from '../../store/authStore'
import api from '../../api/client'
import { useToast } from '../common/Toast'
import { useBrokers, useAddBroker, useAccounts, useAddAccount, useUpdateAccountCapital } from '../../hooks/useTrades'
import { useUsers, useSaveUserProfile, useProfile, useSaveProfile, usePlans, useCreatePlan, useUpdatePlan, useTogglePlan, useSubs } from '../../hooks/useSettings'
import { getCredits } from '../../api/games'
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
            </> : (<>
              <button className={`stab${tab==='accounts'?' active':''}`} onClick={()=>setTab('accounts')}>My Accounts</button>
              <button className={`stab${tab==='gems'?' active':''}`}     onClick={()=>setTab('gems')}>💎 Gems</button>
            </>)}
            <button className={`stab${tab==='profile'?' active':''}`}   onClick={()=>setTab('profile')}>Profile</button>
          </div>

          {tab === 'profile' && (
            <ProfileTab user={user} mobile={mobile} setMobile={setMobile} onSave={saveProfile} />
          )}
          {tab === 'accounts' && <AccountsTab />}
          {tab === 'gems'     && <GemsTab />}
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

const SEGMENTS    = ['equity','derivatives','commodities','currency','mf']
const SEG_LABEL   = { equity:'Equity', derivatives:'Derivatives (F&O)', commodities:'Commodities', currency:'Currency', mf:'Mutual Funds' }
const RISK_OPTS   = ['conservative','moderate','aggressive']
const TYPE_OPTS   = ['trader','investor','both']
const FOCUS_OPTS  = [['self_directed','Self-directed'],['advisory','Advisory / Managed'],['mf_focused','MF Focused']]

function ChipGroup({ label, options, value, multi, onChange }) {
  function toggle(v) {
    if (multi) {
      const cur = value ? value.split(',').filter(Boolean) : []
      const next = cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v]
      onChange(next.join(','))
    } else {
      onChange(value === v ? '' : v)
    }
  }
  const selected = value ? value.split(',').filter(Boolean) : []
  return (
    <div style={{marginBottom:14}}>
      <div style={{fontSize:11,fontWeight:700,color:'#334155',marginBottom:8,textTransform:'uppercase',letterSpacing:.4}}>{label}</div>
      <div style={{display:'flex',flexWrap:'wrap',gap:6}}>
        {options.map(opt => {
          const [v, lbl] = Array.isArray(opt) ? opt : [opt, opt.charAt(0).toUpperCase() + opt.slice(1)]
          const active = selected.includes(v)
          return (
            <div key={v} onClick={() => toggle(v)}
              style={{padding:'6px 14px',border:`1.5px solid ${active?'#3b82f6':'#e2e8f0'}`,borderRadius:20,
                fontSize:12,fontWeight:600,cursor:'pointer',userSelect:'none',transition:'all .15s',
                background:active?'#eff6ff':'#fff',color:active?'#1d4ed8':'#64748b'}}>
              {lbl}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ProfileTab({ user, mobile, setMobile, onSave }) {
  const { data: profile, isLoading } = useProfile()
  const doSave = useSaveProfile()
  const toast  = useToast()

  const [segment,    setSegment]    = useState('')
  const [riskType,   setRiskType]   = useState('')
  const [traderType, setTraderType] = useState('')
  const [focus,      setFocus]      = useState('')

  useEffect(() => {
    if (profile) {
      setSegment(profile.segment    || '')
      setRiskType(profile.risk_type  || '')
      setTraderType(profile.trader_type || '')
      setFocus(profile.focus       || '')
    }
  }, [profile])

  async function savePrefs() {
    const res = await doSave.mutateAsync({ segment, risk_type: riskType, trader_type: traderType, focus, setup_done: true })
    if (res.ok) toast('Preferences saved ✓', 'ok')
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="stab-panel active">
      {/* Identity */}
      <div style={{display:'flex',alignItems:'center',gap:14,padding:'16px 0 14px',borderBottom:'1px solid #f1f5f9',marginBottom:14}}>
        {user.picture
          ? <img src={user.picture} style={{width:52,height:52,borderRadius:'50%',objectFit:'cover',border:'2px solid #e2e8f0',flexShrink:0}} alt="" />
          : <div style={{width:52,height:52,borderRadius:'50%',background:'#3b82f6',display:'flex',alignItems:'center',justifyContent:'center',fontSize:20,fontWeight:700,color:'#fff',flexShrink:0}}>{user.name[0].toUpperCase()}</div>
        }
        <div>
          <div style={{fontSize:15,fontWeight:700,color:'#1e293b'}}>{user.name}</div>
          <div style={{fontSize:12,color:'#64748b',marginTop:2}}>{user.email}</div>
          <span className={`role-chip role-chip-${user.role}`} style={{marginTop:5,display:'inline-block'}}>{user.role.replace('_',' ').toUpperCase()}</span>
        </div>
      </div>

      {/* Contact */}
      <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8}}>Contact</div>
      <div className="form-row">
        <label>Mobile</label>
        <input placeholder="+91 98765 43210" value={mobile} onChange={e=>setMobile(e.target.value)} />
      </div>
      <button className="btn btn-primary btn-sm" onClick={onSave} style={{marginBottom:20}}>Save mobile</button>

      {/* Trading preferences */}
      <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:12,borderTop:'1px solid #f1f5f9',paddingTop:16}}>
        Trading Preferences
      </div>
      {isLoading ? <div style={{color:'var(--muted)',fontSize:13}}>Loading…</div> : <>
        <ChipGroup label="Segments you trade" options={SEGMENTS.map(s => [s, SEG_LABEL[s]])}
                   value={segment} multi onChange={setSegment} />
        <ChipGroup label="Risk appetite" options={RISK_OPTS}
                   value={riskType} multi={false} onChange={setRiskType} />
        <ChipGroup label="You are primarily a" options={TYPE_OPTS}
                   value={traderType} multi={false} onChange={setTraderType} />
        <ChipGroup label="Primary focus" options={FOCUS_OPTS}
                   value={focus} multi={false} onChange={setFocus} />
        <button className="btn btn-primary btn-sm" onClick={savePrefs} disabled={doSave.isPending}>
          Save preferences
        </button>
      </>}

      <div style={{marginTop:20,paddingTop:16,borderTop:'1px solid #f1f5f9'}}>
        <a href={`${AUTH_BASE}/logout`} style={{fontSize:13,color:'var(--red)',fontWeight:600}}>Sign out</a>
      </div>
    </div>
  )
}

// ─── Gems (client) ───────────────────────────────────────────────────────────

const REASON_LABEL = {
  game_win:               '🏆 Game win',
  game_reward:            '🎮 Game reward',
  subscription_purchase:  '🔓 Subscription',
  manual:                 '⚙️ Manual',
  refund:                 '↩️ Refund',
}

function GemsTab() {
  const { data, isLoading } = useQuery({ queryKey: ['credits'], queryFn: getCredits, refetchInterval: 30000 })
  const balance = data?.balance ?? 0
  const history = data?.history ?? []

  function fmtTs(ts) {
    if (!ts) return ''
    const d = new Date(ts.replace('Z','') + (ts.endsWith('Z') ? '' : 'Z'))
    return d.toLocaleString('en-IN', { timeZone:'Asia/Kolkata', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', hour12:true })
  }

  return (
    <div className="stab-panel active">
      {/* Balance card */}
      <div style={{background:'linear-gradient(135deg,#1e1b4b,#312e81)',borderRadius:10,padding:'16px 18px',marginBottom:16,display:'flex',alignItems:'center',justifyContent:'space-between'}}>
        <div>
          <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.6,color:'#a5b4fc',marginBottom:4}}>Gem Balance</div>
          <div style={{fontSize:28,fontWeight:800,color:'#fbbf24'}}>💎 {balance}</div>
        </div>
        <div style={{fontSize:11,color:'#818cf8',textAlign:'right',lineHeight:1.6}}>
          Earn by winning<br/>games &amp; quizzes.<br/>Spend on plans.
        </div>
      </div>

      {/* History */}
      <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8}}>Transaction History</div>
      {isLoading && <div className="empty">Loading…</div>}
      {!isLoading && !history.length && <div className="empty">No transactions yet. Play a game to earn your first gems!</div>}
      {history.map(tx => (
        <div key={tx.id} style={{display:'flex',alignItems:'center',gap:10,padding:'9px 0',borderBottom:'1px solid #f1f5f9'}}>
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontSize:13,fontWeight:600,color:'#1e293b'}}>
              {REASON_LABEL[tx.reason] || tx.reason}
              {tx.note ? <span style={{fontWeight:400,color:'var(--muted)'}}> · {tx.note}</span> : null}
            </div>
            <div style={{fontSize:11,color:'var(--muted)',marginTop:1}}>{fmtTs(tx.created_at)}</div>
          </div>
          <div style={{fontWeight:700,fontSize:14,color: tx.amount > 0 ? 'var(--green)' : 'var(--red)',whiteSpace:'nowrap'}}>
            {tx.amount > 0 ? '+' : ''}{tx.amount} 💎
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── My Accounts (client) ─────────────────────────────────────────────────────

function fmtRs(v) {
  if (v == null) return null
  return '₹' + Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

function AccountCapitalRow({ account }) {
  const toast   = useToast()
  const upd     = useUpdateAccountCapital(account.id)
  const [open,   setOpen]   = useState(false)
  const [action, setAction] = useState('set')  // 'set' | 'add'
  const [amount, setAmount] = useState('')

  async function save() {
    const v = parseFloat(amount)
    if (!v || v <= 0) return toast('Enter a valid amount', 'err')
    const res = await upd.mutateAsync({ action, amount: v })
    if (res.ok) {
      toast(action === 'add' ? `+${fmtRs(v)} added ✓` : `Capital set to ${fmtRs(v)} ✓`, 'ok')
      setOpen(false); setAmount('')
    } else toast(res.error || 'Failed', 'err')
  }

  const name = account.game_id
    ? account.label
    : (account.label || [account.broker, account.account_no].filter(Boolean).join(' · ') || `Account ${account.id}`)

  return (
    <div style={{borderBottom:'1px solid #f1f5f9',paddingBottom:8,marginBottom:8}}>
      <div style={{display:'flex',alignItems:'center',gap:8}}>
        <div style={{flex:1}}>
          <div style={{fontWeight:600,fontSize:13,color:'#1e293b'}}>{name}</div>
          <div style={{fontSize:11,color:'var(--muted)',marginTop:1,display:'flex',gap:8,flexWrap:'wrap'}}>
            {account.broker && !account.game_id && <span>{account.broker}</span>}
            {account.account_no && <span>{account.account_no}</span>}
            {account.capital != null
              ? <span style={{color:'#16a34a',fontWeight:600}}>Capital: {fmtRs(account.capital)}</span>
              : <span style={{color:'#f59e0b'}}>No capital set</span>}
          </div>
        </div>
        {!account.game_id && (
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen(o => !o)}
            style={{fontSize:11,padding:'3px 8px'}}>
            {open ? 'Cancel' : account.capital != null ? '+ Top-up' : 'Set Capital'}
          </button>
        )}
      </div>

      {open && (
        <div style={{marginTop:8,background:'#f8fafc',border:'1px solid var(--border)',borderRadius:6,padding:10,display:'flex',gap:8,alignItems:'flex-end',flexWrap:'wrap'}}>
          <div style={{display:'flex',border:'1px solid var(--border)',borderRadius:6,overflow:'hidden',flexShrink:0}}>
            <button onClick={()=>setAction('set')}
              style={{padding:'5px 10px',fontSize:11,fontWeight:600,border:'none',cursor:'pointer',
                background:action==='set'?'var(--blue)':'#fff',color:action==='set'?'#fff':'var(--muted)'}}>
              Set
            </button>
            <button onClick={()=>setAction('add')}
              style={{padding:'5px 10px',fontSize:11,fontWeight:600,border:'none',cursor:'pointer',
                background:action==='add'?'var(--green)':'#fff',color:action==='add'?'#fff':'var(--muted)'}}>
              Add
            </button>
          </div>
          <div style={{flex:1,minWidth:100}}>
            <input type="number" step="1000" placeholder="Amount (₹)" value={amount}
              onChange={e=>setAmount(e.target.value)}
              style={{width:'100%',padding:'5px 8px',fontSize:13,border:'1px solid var(--border)',borderRadius:6}} />
          </div>
          <button className="btn btn-success btn-sm" onClick={save} disabled={upd.isPending}
            style={{whiteSpace:'nowrap'}}>
            {upd.isPending ? '…' : 'Save'}
          </button>
        </div>
      )}
    </div>
  )
}

function AccountsTab() {
  const { data: accounts = [], isLoading } = useAccounts()
  const { data: brokers  = [] }            = useBrokers()
  const addAccount = useAddAccount()
  const toast      = useToast()
  const [brokerId, setBrokerId] = useState('')
  const [acctNo,   setAcctNo]   = useState('')
  const [label,    setLabel]    = useState('')
  const [capital,  setCapital]  = useState('')

  async function add() {
    if (!brokerId)                         return toast('Select a broker', 'err')
    if (!capital || parseFloat(capital) <= 0) return toast('Enter initial capital', 'err')
    const res = await addAccount.mutateAsync({ broker_id: parseInt(brokerId), account_no: acctNo, label, capital: parseFloat(capital) })
    if (res.ok) { toast('Account added ✓', 'ok'); setBrokerId(''); setAcctNo(''); setLabel(''); setCapital('') }
    else toast(res.error || 'Failed', 'err')
  }

  // Only show real accounts in management (game accounts are managed via game lifecycle)
  const realAccounts = accounts.filter(a => !a.game_id)

  return (
    <div className="stab-panel active">
      <div style={{marginBottom:12}}>
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !realAccounts.length && <div style={{color:'var(--muted)',fontSize:13,padding:'8px 0'}}>No accounts yet.</div>}
        {realAccounts.map(a => <AccountCapitalRow key={a.id} account={a} />)}
      </div>
      <div style={{background:'#f8fafc',border:'1px solid var(--border)',borderRadius:8,padding:12}}>
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
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
          <div className="form-row">
            <label>Label (optional)</label>
            <input placeholder="e.g. Zerodha Main" value={label} onChange={e=>setLabel(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Initial Capital (₹) *</label>
            <input type="number" step="10000" placeholder="e.g. 500000" value={capital} onChange={e=>setCapital(e.target.value)} />
          </div>
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
  const updatePlan = useUpdatePlan()
  const togglePlan = useTogglePlan()
  const toast      = useToast()
  const [name,     setName]     = useState('')
  const [price,    setPrice]    = useState('0')
  const [gemCost,  setGemCost]  = useState('0')
  const [duration, setDuration] = useState('30')
  const [desc,     setDesc]     = useState('')
  const [editGem,  setEditGem]  = useState({})  // { [planId]: gemCostStr }

  async function create() {
    if (!name.trim()) { toast('Enter plan name', 'err'); return }
    const res = await createPlan.mutateAsync({ name: name.trim(), description: desc, price: parseInt(price||0), gem_cost: parseInt(gemCost||0), duration_days: parseInt(duration||30) })
    if (res.ok) { toast('Plan created ✓', 'ok'); setName(''); setPrice('0'); setGemCost('0'); setDuration('30'); setDesc('') }
    else toast(res.error || 'Failed', 'err')
  }

  async function saveGemCost(id) {
    const res = await updatePlan.mutateAsync({ id, gem_cost: parseInt(editGem[id] || 0) })
    if (res.ok) { toast('Gem cost updated ✓', 'ok'); setEditGem(prev => { const n = {...prev}; delete n[id]; return n }) }
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
              <div style={{fontSize:11,color:'var(--muted)',marginBottom:4}}>₹{p.price} · {p.duration_days} days{p.description?` · ${p.description}`:''}</div>
              <div style={{display:'flex',alignItems:'center',gap:6}}>
                <span style={{fontSize:11,color:'var(--muted)'}}>💎 Gems:</span>
                {p.id in editGem ? (
                  <>
                    <input type="number" min="0" value={editGem[p.id]}
                           onChange={e => setEditGem(prev => ({...prev, [p.id]: e.target.value}))}
                           style={{width:60,fontSize:11,padding:'2px 4px',border:'1px solid var(--border)',borderRadius:4}} />
                    <button className="btn btn-primary btn-sm" style={{fontSize:10,padding:'2px 8px'}} onClick={() => saveGemCost(p.id)}>Save</button>
                    <button className="btn btn-ghost btn-sm" style={{fontSize:10,padding:'2px 6px'}} onClick={() => setEditGem(prev => { const n={...prev}; delete n[p.id]; return n })}>✕</button>
                  </>
                ) : (
                  <span style={{fontSize:11,cursor:'pointer',color: p.gem_cost > 0 ? 'var(--text)' : 'var(--muted)'}}
                        onClick={() => setEditGem(prev => ({...prev, [p.id]: String(p.gem_cost || 0)}))}>
                    {p.gem_cost > 0 ? p.gem_cost : <span style={{textDecoration:'underline dotted'}}>Set</span>}
                  </span>
                )}
              </div>
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
            <label>Gem cost 💎</label>
            <input type="number" min="0" value={gemCost} onChange={e=>setGemCost(e.target.value)} />
          </div>
          <div className="form-row">
            <label>Duration (days)</label>
            <input type="number" min="1" value={duration} onChange={e=>setDuration(e.target.value)} />
          </div>
          <div className="form-row" style={{gridColumn:'1/-1'}}>
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
