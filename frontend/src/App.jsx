import { useState } from 'react'
import useAuthStore from './store/authStore'
import useMe from './hooks/useMe'
import usePrices from './hooks/usePrices'
import TickerStrip from './components/nav/TickerStrip'
import MainNav from './components/nav/MainNav'
import SettingsDrawer from './components/drawer/SettingsDrawer'
import { ToastProvider } from './components/common/Toast'
import Dashboard from './screens/Dashboard'
import Games from './screens/Games'
import './index.css'

function AppShell() {
  useMe()
  usePrices()

  const { user, ready } = useAuthStore()
  const [tab, setTab]     = useState('dashboard')
  const [drawer, setDrawer] = useState(false)

  if (!ready) return <div className="empty" style={{marginTop:80}}>Loading…</div>

  if (!user) {
    window.location.href = '/auth/google'
    return null
  }

  return (
    <>
      <TickerStrip />
      <MainNav activeTab={tab} onTabChange={setTab} onOpenDrawer={() => setDrawer(true)} />
      <SettingsDrawer open={drawer} onClose={() => setDrawer(false)} />

      <div style={{ display: tab === 'dashboard' ? 'block' : 'none' }}>
        <Dashboard />
      </div>
      <div style={{ display: tab === 'games' ? 'block' : 'none' }}>
        <Games />
      </div>
    </>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AppShell />
    </ToastProvider>
  )
}
