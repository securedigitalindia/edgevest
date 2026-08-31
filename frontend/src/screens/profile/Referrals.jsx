import { useQuery } from '@tanstack/react-query'
import { getMyReferrals } from '../../api/games'
import PageHeader from '../../components/common/PageHeader'
import { useToast } from '../../components/common/Toast'
import { fmtIstShort } from '../../utils/format'
import { GemIcon, PeopleIcon } from '../../components/common/Icons'
import './Profile.css'
import './Referrals.css'

function shareLink(code) {
  return `${window.location.origin}/?ref=${code}`
}

function inviteText(signupBonus) {
  return signupBonus
    ? `I use EdgeVest for NSE/BSE trade recommendations & live signals — sign up with my link and get ${signupBonus} bonus gems on the house 🎁`
    : "I use EdgeVest for NSE/BSE trade recommendations & live signals — sign up with my link:"
}

export default function Referrals() {
  const toast = useToast()
  const { data, isLoading } = useQuery({ queryKey: ['my-referrals'], queryFn: getMyReferrals })

  const code           = data?.code
  const referredCount  = data?.referred_count ?? 0
  const rewardedCount  = data?.rewarded_count ?? 0
  const gemsEarned     = data?.gems_earned ?? 0
  const history        = data?.referrals ?? []
  const rewardGems     = data?.reward_gems
  const signupBonus    = data?.signup_bonus_gems

  async function copyLink(successMessage = 'Link copied ✓') {
    if (!code) return
    const payload = `${inviteText(signupBonus)}\n${shareLink(code)}`
    try {
      await navigator.clipboard.writeText(payload)
      toast(successMessage, 'ok')
      return
    } catch {
      // navigator.clipboard.writeText throws NotAllowedError whenever the
      // document isn't focused at the exact call moment (e.g. devtools or
      // another window had focus a beat earlier) — legacy execCommand is
      // far more tolerant of that, so fall back to it before giving up.
    }
    try {
      const ta = document.createElement('textarea')
      ta.value = payload
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.focus()
      ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      if (ok) { toast(successMessage, 'ok'); return }
    } catch {
      // fall through to the error toast below
    }
    toast('Could not copy — select the link above instead', 'err')
  }

  async function shareOrCopy() {
    if (!code) return
    const link = shareLink(code)
    if (navigator.share) {
      try {
        await navigator.share({ title: 'Join me on EdgeVest', text: inviteText(signupBonus), url: link })
      } catch (e) {
        if (e?.name === 'AbortError') return // user cancelled the share sheet — not an error
        // A rejected navigator.share() call still consumes this click's
        // transient user-activation, so any second permission-gated API
        // call (clipboard, in either form) chained right here in the same
        // handler would be doomed to fail too — confirmed by direct
        // testing, not a guess. Point at the separate Copy button instead,
        // which gets its own fresh click/activation, rather than silently
        // attempting (and likely failing) a same-handler fallback.
        toast("Sharing isn't available here — use Copy instead", 'err')
      }
    } else {
      copyLink()
    }
  }

  return (
    <div className="profile-page">
      <PageHeader title="Refer & Earn" fallback="/profile" />
      <div className="stab-panel active">
        {/* The offer — shown up front so it's clear why sharing is worth it */}
        {!isLoading && (rewardGems != null || signupBonus != null) && (
          <div className="ref-offer">
            <div className="ref-offer-item">
              <div className="ref-offer-amount"><GemIcon size={15}/> {rewardGems}</div>
              <div className="ref-offer-label">You earn, per friend who joins</div>
            </div>
            <div className="ref-offer-div" aria-hidden="true" />
            <div className="ref-offer-item">
              <div className="ref-offer-amount"><GemIcon size={15}/> {signupBonus}</div>
              <div className="ref-offer-label">They get, for signing up with your link</div>
            </div>
          </div>
        )}

        {/* Code / share card */}
        <div className="ref-code-card">
          <div className="ref-code-label">Your Referral Code</div>
          <div className="ref-code-value">{isLoading ? '···' : (code || '—')}</div>
          <div className="ref-code-link">{code ? shareLink(code) : ''}</div>
          <div className="ref-code-actions">
            <button className="ref-btn ref-btn-primary" onClick={shareOrCopy} disabled={!code}>Share Link</button>
            <button className="ref-btn ref-btn-ghost" onClick={() => copyLink()} disabled={!code}>Copy</button>
          </div>
          <div className="ref-code-hint">Your reward lands once they finish setting up their account — not just at signup.</div>
        </div>

        {/* Stats */}
        <div className="ref-stats">
          <div className="ref-stat">
            <div className="ref-stat-value">{referredCount}</div>
            <div className="ref-stat-label">Referred</div>
          </div>
          <div className="ref-stat">
            <div className="ref-stat-value">{rewardedCount}</div>
            <div className="ref-stat-label">Rewarded</div>
          </div>
          <div className="ref-stat">
            <div className="ref-stat-value" style={{display:'flex',alignItems:'center',gap:4,justifyContent:'center'}}>
              {gemsEarned} <GemIcon size={14}/>
            </div>
            <div className="ref-stat-label">Gems Earned</div>
          </div>
        </div>

        {/* History */}
        <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8}}>Referral History</div>
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !history.length && (
          <div className="empty">
            <PeopleIcon size={20}/>
            <div style={{marginTop:6}}>No referrals yet. Share your link to start earning gems!</div>
          </div>
        )}
        {history.map((r, i) => (
          <div key={r.id ?? i} style={{display:'flex',alignItems:'center',gap:10,padding:'9px 0',borderBottom:'1px solid #f1f5f9'}}>
            <div style={{flex:1,minWidth:0}}>
              <div style={{fontSize:13,fontWeight:600,color:'#1e293b'}}>{r.referee_name || 'EdgeVest user'}</div>
              <div style={{fontSize:11,color:'var(--muted)',marginTop:1}}>
                Joined {fmtIstShort(r.created_at)}
                {r.status === 'rewarded' && r.rewarded_at ? <> · Rewarded {fmtIstShort(r.rewarded_at)}</> : null}
              </div>
            </div>
            <div style={{textAlign:'right'}}>
              <span className={`ref-status ref-status-${r.status}`}>{r.status}</span>
              {r.status === 'rewarded' && rewardGems != null && (
                <div style={{fontSize:11,fontWeight:700,color:'#166534',marginTop:3}}>{rewardGems} gems</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
