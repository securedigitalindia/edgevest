import useAuthStore from '../store/authStore'

export default function Dashboard() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'

  return (
    <div style={{ padding:'20px 24px', maxWidth:1400 }}>
      <div className="empty" style={{ marginTop:60 }}>
        📊 Dashboard — positions &amp; recommendations coming soon.<br />
        <span style={{ fontSize:11, marginTop:8, display:'block', color:'#94a3b8' }}>
          This screen will port the existing {isAdmin ? 'Recommendations + All Positions' : 'My Positions'} view.
        </span>
      </div>
    </div>
  )
}
