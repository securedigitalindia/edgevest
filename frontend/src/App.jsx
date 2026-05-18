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
import SetupWizard from './screens/SetupWizard'
import './index.css'

function AppShell() {
  useMe()
  usePrices()

  const { user, ready } = useAuthStore()
  const [tab, setTab]       = useState('dashboard')
  const [drawer, setDrawer] = useState(false)
  const [drawerTab, setDrawerTab] = useState(null)

  function openDrawer(initialTab) {
    setDrawerTab(initialTab ?? null)
    setDrawer(true)
  }

  if (!ready) return <div className="empty" style={{marginTop:80}}>Loading…</div>

  if (!user) {
    window.location.href = '/auth/google'
    return null
  }

  if (!user.setup_done) {
    return <SetupWizard user={user} />
  }

  return (
    <>
      <TickerStrip />
      <MainNav activeTab={tab} onTabChange={setTab} onOpenDrawer={openDrawer} />
      <SettingsDrawer open={drawer} onClose={() => setDrawer(false)} initialTab={drawerTab} />

      {tab === 'dashboard' && <Dashboard openDrawer={openDrawer} />}
      {tab === 'games'     && <Games />}
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
