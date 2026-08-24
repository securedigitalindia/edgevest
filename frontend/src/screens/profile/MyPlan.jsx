import { useMySubscription } from '../../hooks/useBilling'
import PageHeader from '../../components/common/PageHeader'
import { fmtIstShort } from '../../utils/format'
import './Profile.css'

export default function MyPlan() {
  const { data, isLoading } = useMySubscription()
  const current = data?.current
  const history = data?.history ?? []

  function daysLeft(endDate) {
    if (!endDate) return null
    const diff = Math.ceil((new Date(endDate + 'T00:00:00Z') - new Date()) / 86400000)
    return diff
  }

  function paymentLabel(s) {
    if (s.amount_paid > 0) return `Paid ₹${s.amount_paid}`
    return s.plan_gem_cost > 0 ? 'Redeemed with gems' : 'Free'
  }

  const left = current ? daysLeft(current.end_date) : null

  return (
    <div className="profile-page">
      <PageHeader title="My Plan" fallback="/profile" />
      <div className="stab-panel active">
        {/* Current plan card */}
        <div style={{background:'linear-gradient(135deg,#1e1b4b,#312e81)',borderRadius:10,padding:'16px 18px',marginBottom:16}}>
          {current ? (
            <>
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:6}}>
                <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.6,color:'#a5b4fc'}}>Current Plan</div>
                <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,fontWeight:700,
                              background: current.status==='active' ? '#dcfce7' : '#f1f5f9',
                              color: current.status==='active' ? '#166534' : '#64748b'}}>
                  {current.status}
                </span>
              </div>
              <div style={{fontSize:22,fontWeight:800,color:'#fff',marginBottom:4}}>{current.plan_name}</div>
              <div style={{fontSize:12,color:'#c7d2fe'}}>
                {current.start_date} → {current.end_date}
                {current.status==='active' && left != null && (
                  <span> · {left} day{left===1?'':'s'} left</span>
                )}
              </div>
            </>
          ) : (
            <div style={{color:'#c7d2fe',fontSize:13}}>No active subscription. Check the Dashboard to unlock one.</div>
          )}
        </div>

        {/* History */}
        <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8}}>Subscription History</div>
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !history.length && <div className="empty">No subscription history yet.</div>}
        {history.map(s => (
          <div key={s.id} style={{padding:'9px 0',borderBottom:'1px solid #f1f5f9'}}>
            <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:2}}>
              <span style={{fontSize:13,fontWeight:600,flex:1}}>{s.plan_name}</span>
              <span style={{fontSize:11,padding:'2px 7px',borderRadius:20,fontWeight:600,
                            background:s.status==='active'?'#dcfce7':'#f1f5f9',
                            color:s.status==='active'?'#166534':'#64748b'}}>
                {s.status}
              </span>
            </div>
            <div style={{fontSize:11,color:'var(--muted)',display:'flex',gap:10,flexWrap:'wrap'}}>
              <span>{s.start_date} → {s.end_date}</span>
              <span>{paymentLabel(s)}</span>
              <span>{fmtIstShort(s.created_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
