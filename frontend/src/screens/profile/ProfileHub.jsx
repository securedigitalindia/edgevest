import { useNavigate } from 'react-router-dom'
import { authUrl } from '../../api/client'
import useAuthStore from '../../store/authStore'
import { CardIcon, BankIcon, GemIcon, ProfileIcon, BuildingIcon, PeopleIcon, ClipboardIcon, ReceiptIcon, ChartIcon, BookIcon } from '../../components/common/Icons'
import './Profile.css'

// Role-aware menu row list — mirrors the exact branching that used to drive
// the old settings drawer's tab strip (client: My Plan/My Accounts/Gems/Details,
// admin: Brokers/Users/Plans/Subscriptions + Details).
// `icon` is a component reference (e.g. CardIcon), not a rendered element —
// sized/colored consistently here rather than per call site.
function MenuRow({ icon: Icon, label, onClick }) {
  return (
    <div className="phub-row" onClick={onClick}>
      <span className="phub-row-icon"><Icon size={18}/></span>
      <span className="phub-row-label">{label}</span>
      <span className="phub-row-chevron">›</span>
    </div>
  )
}

export default function ProfileHub() {
  const navigate = useNavigate()
  const user     = useAuthStore(s => s.user)
  const isAdmin  = user?.role === 'super_admin' || user?.role === 'admin'

  if (!user) return null

  return (
    <div className="profile-page">
      {/* Identity header — same avatar/name/email/role-chip markup that used
          to live at the top of the drawer's Profile tab. */}
      <div className="phub-identity">
        {user.picture
          ? <img src={user.picture} className="phub-avatar" alt="" />
          : <div className="phub-avatar-initials">{user.name[0].toUpperCase()}</div>
        }
        <div>
          <div className="phub-name">{user.name}</div>
          <div className="phub-email">{user.email}</div>
          {user.role !== 'client' && (
            <span className={`role-chip role-chip-${user.role}`} style={{marginTop:5,display:'inline-block'}}>{user.role.replace('_',' ').toUpperCase()}</span>
          )}
        </div>
      </div>

      <div className="phub-section">
        {!isAdmin && <>
          <MenuRow icon={CardIcon} label="My Plan"     onClick={() => navigate('/profile/plan')} />
          <MenuRow icon={BankIcon} label="My Accounts" onClick={() => navigate('/profile/accounts')} />
          <MenuRow icon={GemIcon}  label="Gems"        onClick={() => navigate('/profile/gems')} />
          <MenuRow icon={PeopleIcon} label="Refer & Earn" onClick={() => navigate('/profile/referrals')} />
        </>}
        <MenuRow icon={ChartIcon}   label="Monthly Report" onClick={() => navigate('/profile/reports')} />
        <MenuRow icon={BookIcon}    label="Learn" onClick={() => navigate('/profile/learn')} />
        <MenuRow icon={ProfileIcon} label="Details" onClick={() => navigate('/profile/details')} />
      </div>

      {isAdmin && (
        <div className="phub-section">
          <div className="phub-section-title">Admin</div>
          <MenuRow icon={BuildingIcon}  label="Brokers"       onClick={() => navigate('/profile/brokers')} />
          <MenuRow icon={PeopleIcon}    label="Users"          onClick={() => navigate('/profile/users')} />
          <MenuRow icon={ClipboardIcon} label="Plans"          onClick={() => navigate('/profile/plans')} />
          <MenuRow icon={ReceiptIcon}   label="Subscriptions"  onClick={() => navigate('/profile/subscriptions')} />
        </div>
      )}

      <div className="phub-section">
        <button className="phub-signout" onClick={() => window.location.replace(authUrl('/logout'))}>Sign out</button>
      </div>

      <div className="phub-version">EdgeVest v{__APP_VERSION__}</div>
    </div>
  )
}
