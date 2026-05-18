import { useState } from 'react'
import { saveProfile } from '../api/settings'
import './SetupWizard.css'

const SEGMENTS  = [
  ['equity',      'Equity'],
  ['derivatives', 'Derivatives (F&O)'],
  ['commodities', 'Commodities'],
  ['currency',    'Currency'],
  ['mf',          'Mutual Funds'],
]
const RISK_OPTS  = [['conservative','Conservative'],['moderate','Moderate'],['aggressive','Aggressive']]
const TYPE_OPTS  = [['trader','Trader'],['investor','Investor'],['both','Both']]
const FOCUS_OPTS = [['self_directed','Self-directed'],['advisory','Advisory / Managed'],['mf_focused','MF Focused']]

function Chips({ options, value, multi, onChange }) {
  const selected = value ? value.split(',').filter(Boolean) : []
  function toggle(v) {
    if (multi) {
      const next = selected.includes(v) ? selected.filter(x => x !== v) : [...selected, v]
      onChange(next.join(','))
    } else {
      onChange(selected[0] === v ? '' : v)
    }
  }
  return (
    <div className="wiz-chips">
      {options.map(([v, lbl]) => (
        <div key={v} className={`wiz-chip${selected.includes(v) ? ' active' : ''}`} onClick={() => toggle(v)}>
          {lbl}
        </div>
      ))}
    </div>
  )
}

export default function SetupWizard({ user }) {
  const [step,       setStep]       = useState(1)
  const [segment,    setSegment]    = useState('')
  const [riskType,   setRiskType]   = useState('')
  const [traderType, setTraderType] = useState('')
  const [focus,      setFocus]      = useState('')
  const [saving,     setSaving]     = useState(false)
  const [err,        setErr]        = useState('')

  function nextStep() { setErr(''); setStep(s => s + 1) }
  function prevStep() { setErr(''); setStep(s => s - 1) }

  function validateStep2() {
    if (!segment) { setErr('Please select at least one segment.'); return false }
    return true
  }
  function validateStep3() {
    if (!riskType || !traderType || !focus) { setErr('Please complete all selections.'); return false }
    return true
  }

  async function finish() {
    if (!validateStep3()) return
    setSaving(true)
    try {
      const res = await saveProfile({ segment, risk_type: riskType, trader_type: traderType, focus, setup_done: true })
      if (res.ok === false) { setErr(res.error || 'Failed to save. Please try again.'); return }
      // Full reload — App.jsx re-initialises with setup_done:true and checks subscription
      window.location.href = '/app'
    } finally {
      setSaving(false)
    }
  }

  const totalSteps = 3

  return (
    <div className="wiz-overlay">
      <div className="wiz-brand">Dri<span>sh</span>ti</div>

      <div className="wiz-card">
        {/* Progress bar */}
        <div className="wiz-progress">
          {[1,2,3].map(n => (
            <div key={n} className={`wiz-step-dot${n < step ? ' done' : n === step ? ' active' : ''}`} />
          ))}
        </div>

        {/* Step 1 — Welcome */}
        {step === 1 && (
          <div className="wiz-step">
            <div className="wiz-step-lbl">Step 1 of {totalSteps}</div>
            <h2>Welcome to Drishti</h2>
            <p className="wiz-desc">Your profile helps us tailor signals and advisory content to how you trade. This takes about 30 seconds.</p>

            <div className="wiz-identity">
              {user.picture
                ? <img src={user.picture} className="wiz-avatar" alt="" />
                : <div className="wiz-avatar-init">{user.name[0].toUpperCase()}</div>
              }
              <div>
                <div className="wiz-name">{user.name}</div>
                <div className="wiz-email">{user.email}</div>
              </div>
            </div>

            <div className="wiz-actions">
              <button className="wiz-btn-primary" onClick={nextStep}>Get started →</button>
            </div>
          </div>
        )}

        {/* Step 2 — Segments */}
        {step === 2 && (
          <div className="wiz-step">
            <div className="wiz-step-lbl">Step 2 of {totalSteps}</div>
            <h2>What do you trade?</h2>
            <p className="wiz-desc">Select all segments you actively trade in. This helps us surface relevant signals.</p>

            <div className="wiz-field-lbl">Segments <span className="wiz-hint">(select one or more)</span></div>
            <Chips options={SEGMENTS} value={segment} multi onChange={setSegment} />

            {err && <div className="wiz-err">{err}</div>}
            <div className="wiz-actions">
              <button className="wiz-btn-ghost" onClick={prevStep}>← Back</button>
              <button className="wiz-btn-primary" onClick={() => { if (validateStep2()) nextStep() }}>Next →</button>
            </div>
          </div>
        )}

        {/* Step 3 — Trading style */}
        {step === 3 && (
          <div className="wiz-step">
            <div className="wiz-step-lbl">Step 3 of {totalSteps}</div>
            <h2>Your trading style</h2>
            <p className="wiz-desc">A few quick questions to personalise your experience.</p>

            <div className="wiz-field-lbl">Risk appetite</div>
            <Chips options={RISK_OPTS} value={riskType} multi={false} onChange={setRiskType} />

            <div className="wiz-field-lbl">You are primarily a</div>
            <Chips options={TYPE_OPTS} value={traderType} multi={false} onChange={setTraderType} />

            <div className="wiz-field-lbl">Primary focus</div>
            <Chips options={FOCUS_OPTS} value={focus} multi={false} onChange={setFocus} />

            {err && <div className="wiz-err">{err}</div>}
            <div className="wiz-actions">
              <button className="wiz-btn-ghost" onClick={prevStep}>← Back</button>
              <button className="wiz-btn-primary" onClick={finish} disabled={saving}>
                {saving ? 'Saving…' : 'Finish setup'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
