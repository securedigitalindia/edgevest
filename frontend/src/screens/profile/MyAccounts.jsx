import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useToast } from '../../components/common/Toast'
import { useBrokers, useAccounts, useAddAccount, useUpdateAccountCapital } from '../../hooks/useTrades'
import { BankIcon, PlusIcon } from '../../components/common/Icons'
import Dropdown from '../../components/common/Dropdown'
import { fmtRs } from '../../utils/format'
import PageHeader from '../../components/common/PageHeader'
import useAuthStore from '../../store/authStore'
import './Profile.css'

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

  const name = account.label || [account.broker, account.account_no].filter(Boolean).join(' · ') || `Account ${account.id}`
  const caption = [account.broker, account.account_no].filter(Boolean).join(' · ') || 'Broker account'

  return (
    <div className="acct-mgmt-row">
      <div className="acct-mgmt-main">
        <div className="acct-picker-icon"><BankIcon /></div>
        <div className="acct-picker-text">
          <div className="acct-picker-name">{name}</div>
          <div className="acct-picker-caption">{caption}</div>
        </div>
        <div className="acct-mgmt-capital">
          {account.capital != null
            ? <div className="acct-mgmt-capital-val">{fmtRs(account.capital)}</div>
            : <div className="acct-mgmt-capital-warn">No capital set</div>}
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen(o => !o)}
            style={{fontSize:11,padding:'3px 8px'}}>
            {open ? 'Cancel' : account.capital != null ? '+ Top-up' : 'Set Capital'}
          </button>
        </div>
      </div>

      {open && (
        <div className="acct-mgmt-form">
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

export default function MyAccounts() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const { data: accounts = [], isLoading } = useAccounts()
  const { data: brokers  = [] }            = useBrokers()
  const addAccount = useAddAccount()
  const toast      = useToast()
  const [brokerId, setBrokerId] = useState('')
  const [acctNo,   setAcctNo]   = useState('')
  const [label,    setLabel]    = useState('')
  const [capital,  setCapital]  = useState('')

  // Client-only page — GET /api/accounts returns every client's accounts to
  // an admin, but POST /api/accounts and /api/accounts/<id>/capital are both
  // ownership/client-gated server-side, so an admin landing here (not linked
  // from ProfileHub, but reachable by URL) would see every button 403.
  if (isAdmin) return <Navigate to="/profile" replace />

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
    <div className="profile-page">
      <PageHeader title="My Accounts" fallback="/profile" />

      <div className="card" style={{marginBottom:14}}>
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !realAccounts.length && (
          <div style={{textAlign:'center',padding:'28px 20px'}}>
            <div style={{color:'var(--muted)',display:'flex',justifyContent:'center',marginBottom:10}}><BankIcon size={30}/></div>
            <div style={{fontSize:14,fontWeight:700,marginBottom:6}}>No accounts yet</div>
            <div style={{fontSize:13,color:'var(--muted)'}}>Add a brokerage account below to start tracking your own positions.</div>
          </div>
        )}
        {realAccounts.map(a => <AccountCapitalRow key={a.id} account={a} />)}
      </div>

      <div className="card">
        <div className="card-header acct-add-header">
          <span style={{display:'inline-flex',color:'var(--blue)'}}><PlusIcon size={14} /></span>
          <h2>Add Account</h2>
        </div>
        <div className="card-body">
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
            <div className="form-row">
              <label>Broker</label>
              <Dropdown variant="form" value={brokerId} onChange={setBrokerId} placeholder="Select…"
                options={brokers.map(b => ({ value: String(b.id), label: b.name }))} />
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
    </div>
  )
}
