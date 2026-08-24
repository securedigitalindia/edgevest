import { Navigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useSubs } from '../../hooks/useSettings'
import PageHeader from '../../components/common/PageHeader'
import './Profile.css'

export default function Subscriptions() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const { data: subs = [], isLoading } = useSubs()

  if (!isAdmin) return <Navigate to="/profile" replace />

  return (
    <div className="profile-page">
      <PageHeader title="Subscriptions" fallback="/profile" />
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
    </div>
  )
}
