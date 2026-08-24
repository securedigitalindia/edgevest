import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useToast } from '../../components/common/Toast'
import { useBrokers, useAddBroker } from '../../hooks/useTrades'
import PageHeader from '../../components/common/PageHeader'
import './Profile.css'

export default function Brokers() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const { data: brokers = [], isLoading } = useBrokers()
  const addBroker = useAddBroker()
  const toast     = useToast()
  const [name, setName] = useState('')

  if (!isAdmin) return <Navigate to="/profile" replace />

  async function add() {
    if (!name.trim()) { toast('Enter broker name', 'err'); return }
    const res = await addBroker.mutateAsync({ name: name.trim() })
    if (res.ok) { toast('Broker added ✓', 'ok'); setName('') }
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="profile-page">
      <PageHeader title="Brokers" fallback="/profile" />
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
    </div>
  )
}
