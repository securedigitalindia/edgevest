import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useToast } from '../../components/common/Toast'
import { usePlans, useCreatePlan, useUpdatePlan, useTogglePlan } from '../../hooks/useSettings'
import PageHeader from '../../components/common/PageHeader'
import './Profile.css'

export default function Plans() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'

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
  const [editPrice, setEditPrice] = useState({}) // { [planId]: priceStr }

  if (!isAdmin) return <Navigate to="/profile" replace />

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

  async function savePrice(id) {
    const res = await updatePlan.mutateAsync({ id, price: parseInt(editPrice[id] || 0) })
    if (res.ok) { toast('Price updated ✓', 'ok'); setEditPrice(prev => { const n = {...prev}; delete n[id]; return n }) }
    else toast(res.error || 'Failed', 'err')
  }

  async function toggle(id, active) {
    const res = await togglePlan.mutateAsync({ id, active: !active })
    if (res.ok) toast(`Plan ${active ? 'disabled' : 'enabled'} ✓`, 'ok')
    else toast(res.error || 'Failed', 'err')
  }

  return (
    <div className="profile-page">
      <PageHeader title="Plans" fallback="/profile" />
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
                <div style={{fontSize:11,color:'var(--muted)',marginBottom:4}}>{p.duration_days} days{p.description?` · ${p.description}`:''}</div>
                <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:4}}>
                  <span style={{fontSize:11,color:'var(--muted)'}}>₹ Price:</span>
                  {p.id in editPrice ? (
                    <>
                      <input type="number" min="0" value={editPrice[p.id]}
                             onChange={e => setEditPrice(prev => ({...prev, [p.id]: e.target.value}))}
                             style={{width:60,fontSize:11,padding:'2px 4px',border:'1px solid var(--border)',borderRadius:4}} />
                      <button className="btn btn-primary btn-sm" style={{fontSize:10,padding:'2px 8px'}} onClick={() => savePrice(p.id)}>Save</button>
                      <button className="btn btn-ghost btn-sm" style={{fontSize:10,padding:'2px 6px'}} onClick={() => setEditPrice(prev => { const n={...prev}; delete n[p.id]; return n })}>✕</button>
                    </>
                  ) : (
                    <span style={{fontSize:11,cursor:'pointer',color: p.price > 0 ? 'var(--text)' : 'var(--muted)'}}
                          onClick={() => setEditPrice(prev => ({...prev, [p.id]: String(p.price || 0)}))}>
                      {p.price > 0 ? `₹${p.price}` : <span style={{textDecoration:'underline dotted'}}>Set</span>}
                    </span>
                  )}
                </div>
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
    </div>
  )
}
