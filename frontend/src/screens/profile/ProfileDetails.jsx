import { useState, useEffect } from 'react'
import useAuthStore from '../../store/authStore'
import api from '../../api/client'
import { useToast } from '../../components/common/Toast'
import { useProfile, useSaveProfile } from '../../hooks/useSettings'
import PageHeader from '../../components/common/PageHeader'
import './Profile.css'

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

export default function ProfileDetails() {
  const user = useAuthStore(s => s.user)
  const { data: profile, isLoading } = useProfile()
  const doSave = useSaveProfile()
  const toast  = useToast()

  const [mobile,     setMobile]     = useState(user?.mobile || '')
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

  async function saveProfile() {
    const res = await api.post(`/users/${user.id}/profile`, { mobile })
    if (res.data.ok) toast('Profile saved', 'ok')
    else toast(res.data.error || 'Error', 'err')
  }

  async function savePrefs() {
    const res = await doSave.mutateAsync({ segment, risk_type: riskType, trader_type: traderType, focus, setup_done: true })
    if (res.ok) toast('Preferences saved ✓', 'ok')
    else toast(res.error || 'Failed', 'err')
  }

  if (!user) return null

  return (
    <div className="profile-page">
      <PageHeader title="Details" fallback="/profile" />
      <div className="stab-panel active">
        {/* Identity */}
        <div style={{display:'flex',alignItems:'center',gap:14,padding:'0 0 14px',borderBottom:'1px solid #f1f5f9',marginBottom:14}}>
          {user.picture
            ? <img src={user.picture} style={{width:52,height:52,borderRadius:'50%',objectFit:'cover',border:'2px solid #e2e8f0',flexShrink:0}} alt="" />
            : <div style={{width:52,height:52,borderRadius:'50%',background:'#3b82f6',display:'flex',alignItems:'center',justifyContent:'center',fontSize:20,fontWeight:700,color:'#fff',flexShrink:0}}>{user.name[0].toUpperCase()}</div>
          }
          <div>
            <div style={{fontSize:15,fontWeight:700,color:'#1e293b'}}>{user.name}</div>
            <div style={{fontSize:12,color:'#64748b',marginTop:2}}>{user.email}</div>
            {user.role !== 'client' && (
              <span className={`role-chip role-chip-${user.role}`} style={{marginTop:5,display:'inline-block'}}>{user.role.replace('_',' ').toUpperCase()}</span>
            )}
          </div>
        </div>

        {/* Contact */}
        <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8}}>Contact</div>
        <div className="form-row">
          <label>Mobile</label>
          <input placeholder="+91 98765 43210" value={mobile} onChange={e=>setMobile(e.target.value)} />
        </div>
        <button className="btn btn-primary btn-sm" onClick={saveProfile} style={{marginBottom:20}}>Save mobile</button>

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
      </div>
    </div>
  )
}
