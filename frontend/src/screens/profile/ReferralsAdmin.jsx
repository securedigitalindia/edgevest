import { useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import useAuthStore from '../../store/authStore'
import { listAllReferrals } from '../../api/games'
import PageHeader from '../../components/common/PageHeader'
import { GemIcon, PeopleIcon } from '../../components/common/Icons'
import { fmtIstShort } from '../../utils/format'
import './Profile.css'
import './Referrals.css'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'rewarded', label: 'Rewarded' },
]

function ReferralRow({ r }) {
  return (
    <div style={{padding:'10px 0',borderBottom:'1px solid #f1f5f9'}}>
      <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:3}}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontSize:13,fontWeight:600,color:'#1e293b',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
            {r.referrer_name} <span style={{color:'var(--muted)',fontWeight:400}}>referred</span> {r.referee_name}
          </div>
        </div>
        <span className={`ref-status ref-status-${r.status}`}>{r.status}</span>
      </div>
      <div style={{fontSize:11,color:'var(--muted)',display:'flex',gap:10,flexWrap:'wrap',marginBottom:3}}>
        <span title="Referrer email">{r.referrer_email}</span>
        <span>→</span>
        <span title="Referee email">{r.referee_email}</span>
      </div>
      <div style={{fontSize:11,color:'#94a3b8',display:'flex',gap:12,flexWrap:'wrap',alignItems:'center'}}>
        <span>Joined {fmtIstShort(r.created_at)}</span>
        {r.status === 'rewarded' && r.rewarded_at && <span>Rewarded {fmtIstShort(r.rewarded_at)}</span>}
        {r.signup_bonus_gems != null && (
          <span style={{display:'flex',alignItems:'center',gap:3,color:'#0369a1'}}>
            <GemIcon size={11}/> {r.signup_bonus_gems} to referee
          </span>
        )}
        {r.reward_gems != null && (
          <span style={{display:'flex',alignItems:'center',gap:3,color:'#166534'}}>
            <GemIcon size={11}/> {r.reward_gems} to referrer
          </span>
        )}
      </div>
    </div>
  )
}

function TopReferrerRow({ t, rank }) {
  return (
    <div style={{display:'flex',alignItems:'center',gap:10,padding:'8px 0',borderBottom:'1px solid #f1f5f9'}}>
      <div style={{width:20,fontSize:12,fontWeight:700,color:'var(--muted)',flexShrink:0}}>#{rank}</div>
      <div style={{flex:1,minWidth:0}}>
        <div style={{fontSize:13,fontWeight:600,color:'#1e293b',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.name}</div>
        <div style={{fontSize:11,color:'var(--muted)'}}>{t.email}</div>
      </div>
      <div style={{textAlign:'right',flexShrink:0}}>
        <div style={{fontSize:13,fontWeight:700,color:'#166534',display:'flex',alignItems:'center',gap:3,justifyContent:'flex-end'}}>
          <GemIcon size={12}/> {t.gems_earned}
        </div>
        <div style={{fontSize:10,color:'var(--muted)'}}>{t.referred_count} referred · {t.rewarded_count} rewarded</div>
      </div>
    </div>
  )
}

export default function ReferralsAdmin() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const { data, isLoading } = useQuery({ queryKey: ['referrals-admin'], queryFn: listAllReferrals })
  const [status, setStatus] = useState('all')

  const referrals = data?.referrals ?? []
  const summary   = data?.summary ?? {}
  const topReferrers = data?.top_referrers ?? []

  const filtered = useMemo(
    () => referrals.filter(r => status === 'all' || r.status === status),
    [referrals, status]
  )

  if (!isAdmin) return <Navigate to="/profile" replace />

  return (
    <div className="profile-page">
      <PageHeader title="Refer & Earn — Admin" fallback="/profile" />

      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:8}}>
        <div style={{background:'var(--card)',border:'1px solid var(--border)',borderRadius:8,padding:'10px 12px'}}>
          <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:.4}}>Total referrals</div>
          <div style={{fontSize:16,fontWeight:800,color:'#1e293b'}}>{summary.total_referrals ?? 0}</div>
          <div style={{fontSize:10,color:'var(--muted)'}}>{summary.pending_count ?? 0} pending · {summary.rewarded_count ?? 0} rewarded</div>
        </div>
        <div style={{background:'var(--card)',border:'1px solid var(--border)',borderRadius:8,padding:'10px 12px'}}>
          <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:.4}}>Gems paid out</div>
          <div style={{fontSize:16,fontWeight:800,color:'#166534',display:'flex',alignItems:'center',gap:4}}>
            <GemIcon size={14}/> {(summary.signup_bonus_gems_paid ?? 0) + (summary.reward_gems_paid ?? 0)}
          </div>
          <div style={{fontSize:10,color:'var(--muted)'}}>{summary.signup_bonus_gems_paid ?? 0} signup · {summary.reward_gems_paid ?? 0} referrer reward</div>
        </div>
      </div>

      {topReferrers.length > 0 && (
        <div className="stab-panel active" style={{marginBottom:14}}>
          <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:6}}>Top Referrers</div>
          {topReferrers.map((t, i) => <TopReferrerRow key={t.id} t={t} rank={i + 1} />)}
        </div>
      )}

      <div style={{display:'flex',gap:6,marginBottom:10,flexWrap:'wrap'}}>
        {FILTERS.map(f => (
          <button key={f.key} onClick={() => setStatus(f.key)}
            className="btn btn-sm"
            style={{
              padding:'4px 11px', borderRadius:20, fontSize:11, fontWeight:700, border:'1px solid var(--border)',
              background: status === f.key ? '#1e293b' : 'var(--card)',
              color: status === f.key ? '#fff' : 'var(--text)',
            }}>
            {f.label}
          </button>
        ))}
      </div>

      <div className="stab-panel active">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !filtered.length && (
          <div className="empty">
            <PeopleIcon size={20}/>
            <div style={{marginTop:6}}>No referrals found.</div>
          </div>
        )}
        {filtered.map(r => <ReferralRow key={r.id} r={r} />)}
      </div>
    </div>
  )
}
