import { useMemo, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { usePayments, useReconcilePayment } from '../../hooks/useBilling'
import { useToast } from '../../components/common/Toast'
import PageHeader from '../../components/common/PageHeader'
import { RefreshIcon } from '../../components/common/Icons'
import { fmtRs, fmtIstShort } from '../../utils/format'
import './Profile.css'

const OUTCOME_MSG = {
  synced:             { msg: 'Payment found on gateway — subscription activated ✓', type: 'ok' },
  duplicate_refunded: { msg: 'Already covered — payment refunded as a duplicate', type: 'ok' },
  still_pending:      { msg: 'Still not captured on the gateway — nothing to do yet', type: 'ok' },
}

const STATUS_META = {
  paid:               { label: 'Paid',      bg: '#dcfce7', fg: '#166534' },
  created:            { label: 'Pending',   bg: '#fef9c3', fg: '#854d0e' },
  duplicate_refunded: { label: 'Refunded',  bg: '#fef2f2', fg: '#dc2626' },
}

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'paid', label: 'Paid' },
  { key: 'created', label: 'Pending' },
  { key: 'duplicate_refunded', label: 'Refunded' },
]

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || { label: status, bg: '#f1f5f9', fg: '#64748b' }
  return (
    <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,fontWeight:700,background:meta.bg,color:meta.fg,flexShrink:0}}>
      {meta.label}
    </span>
  )
}

function PaymentRow({ p, onReconcile, reconciling }) {
  const meta = STATUS_META[p.status] || { fg: '#64748b' }
  return (
    <div style={{padding:'10px 0',borderBottom:'1px solid #f1f5f9',borderLeft:`3px solid ${meta.fg}`,paddingLeft:10}}>
      <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:3}}>
        <span style={{fontSize:13,fontWeight:600,flex:1,minWidth:0,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{p.user_name}</span>
        <span style={{fontSize:13,fontWeight:700}}>{fmtRs(p.amount)}</span>
        <StatusBadge status={p.status} />
        {p.status === 'created' && (
          <button className="btn btn-ghost btn-sm" title="Check this order against the payment gateway now"
            style={{fontSize:11,padding:'2px 6px',display:'flex',alignItems:'center',gap:4,flexShrink:0}}
            disabled={reconciling} onClick={() => onReconcile(p.id)}>
            <RefreshIcon size={11} /> {reconciling ? 'Checking…' : 'Refresh'}
          </button>
        )}
      </div>
      <div style={{fontSize:11,color:'var(--muted)',display:'flex',gap:10,flexWrap:'wrap',marginBottom:3}}>
        <span>{p.email}</span>
        <span>{p.plan_name}</span>
        <span>{fmtIstShort(p.created_at)}</span>
      </div>
      <div style={{fontSize:10,color:'#94a3b8',fontFamily:'monospace',display:'flex',gap:10,flexWrap:'wrap'}}>
        <span title="Razorpay order id">order: {p.razorpay_order_id}</span>
        {p.razorpay_payment_id && <span title="Razorpay payment id">pay: {p.razorpay_payment_id}</span>}
      </div>
      {p.status === 'duplicate_refunded' && (
        <div style={{fontSize:10,color:'#dc2626',marginTop:3}}>
          Refunded{p.refunded_at ? ` ${fmtIstShort(p.refunded_at)}` : ''} — duplicate of order {p.duplicate_of_order_id || 'unknown'}
          {p.refund_id ? ` · refund ${p.refund_id}` : ''}
        </div>
      )}
    </div>
  )
}

export default function Payments() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const { data: payments = [], isLoading } = usePayments()
  const reconcile = useReconcilePayment()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState('all')
  const q = params.get('u') || ''

  function handleReconcile(orderId) {
    // client.js's response interceptor resolves failed requests to
    // { ok: false, error } rather than rejecting — only onSuccess ever fires.
    reconcile.mutate(orderId, {
      onSuccess: res => {
        if (!res.ok) { toast(res.error || 'Check failed', 'err'); return }
        const known = OUTCOME_MSG[res.outcome]
        toast(known ? known.msg : res.outcome, known?.type || 'ok')
      },
    })
  }

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return payments.filter(p => {
      if (status !== 'all' && p.status !== status) return false
      if (!needle) return true
      return p.email?.toLowerCase().includes(needle) || p.user_name?.toLowerCase().includes(needle)
    })
  }, [payments, status, q])

  const totals = useMemo(() => {
    const paid = payments.filter(p => p.status === 'paid')
    return {
      paidAmount: paid.reduce((sum, p) => sum + (p.amount || 0), 0),
      paidCount:  paid.length,
      pendingCount: payments.filter(p => p.status === 'created').length,
      refundedCount: payments.filter(p => p.status === 'duplicate_refunded').length,
    }
  }, [payments])

  if (!isAdmin) return <Navigate to="/profile" replace />

  return (
    <div className="profile-page">
      <PageHeader title="Payments" fallback="/profile" />

      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:8,marginBottom:14}}>
        <div style={{background:'var(--card)',border:'1px solid var(--border)',borderRadius:8,padding:'10px 12px'}}>
          <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:.4}}>Collected</div>
          <div style={{fontSize:16,fontWeight:800,color:'#166534'}}>{fmtRs(totals.paidAmount)}</div>
          <div style={{fontSize:10,color:'var(--muted)'}}>{totals.paidCount} payment{totals.paidCount===1?'':'s'}</div>
        </div>
        <div style={{background:'var(--card)',border:'1px solid var(--border)',borderRadius:8,padding:'10px 12px'}}>
          <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:.4}}>Pending</div>
          <div style={{fontSize:16,fontWeight:800,color:'#854d0e'}}>{totals.pendingCount}</div>
          <div style={{fontSize:10,color:'var(--muted)'}}>abandoned/in-progress</div>
        </div>
        <div style={{background:'var(--card)',border:'1px solid var(--border)',borderRadius:8,padding:'10px 12px'}}>
          <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:.4}}>Refunded</div>
          <div style={{fontSize:16,fontWeight:800,color:'#dc2626'}}>{totals.refundedCount}</div>
          <div style={{fontSize:10,color:'var(--muted)'}}>duplicate charges</div>
        </div>
      </div>

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
        {q && (
          <button className="btn btn-ghost btn-sm" style={{fontSize:11}}
            onClick={() => setParams(p => { const n = new URLSearchParams(p); n.delete('u'); return n })}>
            Clear filter: {q} ✕
          </button>
        )}
      </div>

      <div className="stab-panel active">
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !filtered.length && <div className="empty">No payments found.</div>}
        {filtered.map(p => (
          <PaymentRow key={p.id} p={p} onReconcile={handleReconcile}
            reconciling={reconcile.isPending && reconcile.variables === p.id} />
        ))}
      </div>
    </div>
  )
}
