import { useState } from 'react'
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

function SummaryTile({ label, value, sub, color }) {
  return (
    <div style={{background:'var(--card)',border:'1px solid var(--border)',borderRadius:8,padding:'10px 12px'}}>
      <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:.4}}>{label}</div>
      <div style={{fontSize:16,fontWeight:800,color}}>{value}</div>
      {sub && <div style={{fontSize:10,color:'var(--muted)'}}>{sub}</div>}
    </div>
  )
}

// "2y 4m" / "7m" / "12d" — first_subscribed is a plain "YYYY-MM-DD" date
// string (same format subscriptions.start_date is stored/displayed in
// elsewhere on this page), so a straight Date() parse + day-diff is enough.
function tenureLabel(firstSubscribed) {
  if (!firstSubscribed) return null
  const days = Math.floor((Date.now() - new Date(firstSubscribed).getTime()) / 86400000)
  if (days < 0) return null
  if (days < 30) return `${days}d`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}m`
  return `${Math.floor(months / 12)}y ${months % 12}m`
}

const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
function monthLabel(m) {
  const [y, mo] = m.split('-').map(Number)
  return `${MONTH_NAMES[mo - 1]} '${String(y).slice(2)}`
}

const TREND_FILTERS = [
  { key: 'paid', label: 'Paid' },
  { key: 'gems', label: 'Gems' },
  { key: 'both', label: 'Both' },
]

const TREND_TITLE = {
  paid: 'Paid Clients — Month on Month',
  gems: 'Gems Clients — Month on Month',
  both: 'Paid + Gems Clients — Month on Month',
}

// Both tracks (money vs. gems) are mutually exclusive per subscription — see
// get_subscription_admin_summary()'s free/paid/gems split — so "Both" is a
// plain sum for the client-count bar, never double-counting the same user.
function trendValue(d, filter) {
  if (filter === 'paid') return d.active_paid_clients
  if (filter === 'gems') return d.active_gems_clients
  return d.active_paid_clients + d.active_gems_clients
}

// Money and gems are different units — "Both" lists them side by side rather
// than summing into one misleading figure.
function trendSubtext(d, filter) {
  if (filter === 'paid') return `${d.new_paid_orders} payment${d.new_paid_orders===1?'':'s'} · ${fmtRs(d.revenue)}`
  if (filter === 'gems') return `${d.new_gems_redemptions} redemption${d.new_gems_redemptions===1?'':'s'} · ${d.gems_spent} gems`
  return `${d.new_paid_orders} payment${d.new_paid_orders===1?'':'s'} + ${d.new_gems_redemptions} redemption${d.new_gems_redemptions===1?'':'s'} · ${fmtRs(d.revenue)} + ${d.gems_spent} gems`
}

// churned/active_new reconcile EXACTLY with the active-client count (see
// get_monthly_subscription_trend()'s docstring): active[this] = active[prev]
// - churned + active_new, always, by construction. This is a distinct
// concept from new_paid_orders/new_gems_redemptions above (a raw payment
// count, which includes renewals by clients who were already active) — the
// two "new" numbers can legitimately disagree, which is exactly the doubt
// this reconciliation line exists to resolve.
function trendChurned(d, filter) {
  if (filter === 'paid') return d.churned_paid_clients
  if (filter === 'gems') return d.churned_gems_clients
  return d.churned_paid_clients + d.churned_gems_clients
}
function trendActiveNew(d, filter) {
  if (filter === 'paid') return d.active_new_paid_clients
  if (filter === 'gems') return d.active_new_gems_clients
  return d.active_new_paid_clients + d.active_new_gems_clients
}
function netChangeBadge(d, filter) {
  const net = trendActiveNew(d, filter) - trendChurned(d, filter)
  if (net === 0) return <span style={{fontSize:9,color:'#94a3b8'}}>–</span>
  return <span style={{fontSize:9,fontWeight:700,color: net > 0 ? '#166534' : '#dc2626'}}>{net > 0 ? `▲${net}` : `▼${Math.abs(net)}`}</span>
}

// Hand-rolled, no charting dependency — same posture as ReportCharts.jsx.
// One series drives the bar height/hue at a time (Paid/Gems/Both, picked by
// the filter above); the flow numbers (new orders/redemptions, revenue/gems
// spent) ride along as plain text underneath rather than a second axis
// (never dual-axis — two measures of different scale get two encodings, not
// one chart with two scales).
function MonthlyTrend({ data }) {
  const [filter, setFilter] = useState('paid')
  if (!data.length) return null
  const max = Math.max(1, ...data.map(d => trendValue(d, filter)))
  return (
    <div className="stab-panel active" style={{marginBottom:14}}>
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:8,marginBottom:2}}>
        <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)'}}>
          {TREND_TITLE[filter]}
        </div>
        <div style={{display:'flex',gap:4}}>
          {TREND_FILTERS.map(f => (
            <button key={f.key} onClick={() => setFilter(f.key)}
              className="btn btn-sm"
              style={{
                padding:'3px 10px', borderRadius:20, fontSize:10, fontWeight:700, border:'1px solid var(--border)',
                background: filter === f.key ? '#1e293b' : 'var(--card)',
                color: filter === f.key ? '#fff' : 'var(--text)',
              }}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div style={{fontSize:9.5,color:'#94a3b8',marginBottom:8}}>
        Each bar is a snapshot of clients active at that month's end — not cumulative. ▲/▼ is the net change vs. the previous month (newly-active minus churned).
      </div>
      <div style={{display:'flex',alignItems:'flex-end',gap:8,height:88}}>
        {data.map(d => {
          const val = trendValue(d, filter)
          const h = Math.max(4, Math.round((val / max) * 60))
          const churned = trendChurned(d, filter), activeNew = trendActiveNew(d, filter)
          return (
            <div key={d.month} style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'flex-end',gap:2,height:'100%'}}>
              <div style={{fontSize:11,fontWeight:700,color:'#1e293b'}}>{val}</div>
              {netChangeBadge(d, filter)}
              <div
                title={`${val} active client${val===1?'':'s'} in ${monthLabel(d.month)} — ${churned} churned, ${activeNew} newly active vs. last month · ${trendSubtext(d, filter)} this month`}
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
              {trendSubtext(d, filter)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function LongestActiveRow({ c, rank }) {
  const renewed = c.total_subscriptions > 1
  return (
    <div style={{display:'flex',alignItems:'center',gap:10,padding:'8px 0',borderBottom:'1px solid #f1f5f9'}}>
      <div style={{width:20,fontSize:12,fontWeight:700,color:'var(--muted)',flexShrink:0}}>#{rank}</div>
      <div style={{flex:1,minWidth:0}}>
        <div style={{fontSize:13,fontWeight:600,color:'#1e293b',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{c.user_name}</div>
        <div style={{fontSize:11,color:'var(--muted)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{c.email}</div>
      </div>
      <div style={{textAlign:'right',flexShrink:0}}>
        <div style={{fontSize:12,fontWeight:700,color:'#1e293b'}}>{tenureLabel(c.first_subscribed)} <span style={{fontWeight:400,color:'var(--muted)'}}>on EdgeVest</span></div>
        <div style={{fontSize:10,color:renewed?'#0369a1':'var(--muted)',marginTop:1}}>
          {c.current_plan_name}{renewed ? ` · renewed ${c.total_subscriptions - 1}x` : ''}
        </div>
      </div>
    </div>
  )
}

export default function Subscriptions() {
  const user     = useAuthStore(s => s.user)
  const isAdmin  = user?.role === 'super_admin' || user?.role === 'admin'
  const navigate = useNavigate()
  const { data, isLoading } = useSubs()
  const subs    = data?.subscriptions ?? []
  const summary = data?.summary ?? {}
  const longestActive = data?.longest_active_clients ?? []
  const monthlyTrend = data?.monthly_trend ?? []

  if (!isAdmin) return <Navigate to="/profile" replace />

  const viewPayments = email => navigate(`/profile/payments?u=${encodeURIComponent(email)}`)

  return (
    <div className="profile-page">
      <PageHeader title="Subscriptions" fallback="/profile" />

      {!isLoading && (
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(90px, 1fr))',gap:8,marginBottom:14}}>
          <SummaryTile label="Paid"     value={summary.paid_count ?? 0}   color="#166534" />
          <SummaryTile label="Gems"     value={summary.gems_count ?? 0}   color="#0369a1" />
          {summary.free_count > 0 && <SummaryTile label="Free" value={summary.free_count} color="#334155" />}
          <SummaryTile label="Renewed"  value={summary.renewed_count ?? 0} color="#7c3aed" sub="resubscribed ≥1x" />
          <SummaryTile label="No Subscription" value={summary.no_sub_count ?? 0} color="#854d0e"
            sub={summary.total_clients != null ? `of ${summary.total_clients} clients` : undefined} />
        </div>
      )}

      <MonthlyTrend data={monthlyTrend} />

      {longestActive.length > 0 && (
        <div className="stab-panel active" style={{marginBottom:14}}>
          <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:6}}>
            Longest-Active Clients
          </div>
          {longestActive.map((c, i) => <LongestActiveRow key={c.user_id} c={c} rank={i + 1} />)}
        </div>
      )}

      <div className="stab-panel active">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !subs.length && <div className="empty">No subscriptions.</div>}
        {subs.map(s => <SubRow key={s.id} s={s} onViewPayments={viewPayments} />)}
      </div>
    </div>
  )
}
