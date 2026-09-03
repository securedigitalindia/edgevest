import { useNavigate, Navigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useSubs } from '../../hooks/useSettings'
import PageHeader from '../../components/common/PageHeader'
import { fmtRs } from '../../utils/format'
import './Profile.css'

function paymentLabel(s) {
  if (s.amount_paid > 0) return `Paid ${fmtRs(s.amount_paid)}`
  return s.plan_gem_cost > 0 ? 'Redeemed with gems' : 'Free'
}

function SubRow({ s, onViewPayments }) {
  const active = s.status === 'active'
  return (
    <div
      style={{padding:'11px 0',borderBottom:'1px solid #f1f5f9',display:'flex',gap:10,alignItems:'flex-start',cursor:s.amount_paid>0?'pointer':'default'}}
      onClick={s.amount_paid > 0 ? () => onViewPayments(s.email) : undefined}
    >
      <div style={{width:30,height:30,borderRadius:'50%',background:active?'#3b82f6':'#94a3b8',display:'flex',alignItems:'center',justifyContent:'center',fontSize:12,fontWeight:700,color:'#fff',flexShrink:0}}>
        {s.user_name?.[0]?.toUpperCase()}
      </div>
      <div style={{flex:1,minWidth:0}}>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <span style={{fontSize:13,fontWeight:600,color:'#1e293b',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{s.user_name}</span>
          <span style={{fontSize:11,color:'var(--muted)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1,minWidth:0}}>{s.email}</span>
        </div>
        <div style={{fontSize:12,color:'#334155',marginTop:2}}>
          {s.plan_name} <span style={{color:'#cbd5e1'}}>·</span> <span style={{color:'var(--muted)'}}>{s.start_date} – {s.end_date}</span>
        </div>
      </div>
      <div style={{textAlign:'right',flexShrink:0}}>
        <div style={{fontSize:11,padding:'2px 8px',borderRadius:20,fontWeight:600,marginBottom:4,
                      background:active?'#dcfce7':'#f1f5f9', color:active?'#166534':'#64748b'}}>
          {s.status}
        </div>
        <div style={{fontSize:11,fontWeight:600,color: s.amount_paid > 0 ? '#1d4ed8' : 'var(--muted)'}}>
          {paymentLabel(s)}{s.amount_paid > 0 ? ' ›' : ''}
        </div>
      </div>
    </div>
  )
}

export default function Subscriptions() {
  const user     = useAuthStore(s => s.user)
  const isAdmin  = user?.role === 'super_admin' || user?.role === 'admin'
  const navigate = useNavigate()
  const { data: subs = [], isLoading } = useSubs()

  if (!isAdmin) return <Navigate to="/profile" replace />

  const viewPayments = email => navigate(`/profile/payments?u=${encodeURIComponent(email)}`)

  return (
    <div className="profile-page">
      <PageHeader title="Subscriptions" fallback="/profile" />
      <div className="stab-panel active">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !subs.length && <div className="empty">No subscriptions.</div>}
        {subs.map(s => <SubRow key={s.id} s={s} onViewPayments={viewPayments} />)}
      </div>
    </div>
  )
}
