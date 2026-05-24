import { useState } from 'react'
import useAuthStore from './store/authStore'
import useMe from './hooks/useMe'
import TickerStrip from './components/nav/TickerStrip'
import MainNav from './components/nav/MainNav'
import SettingsDrawer from './components/drawer/SettingsDrawer'
import { ToastProvider } from './components/common/Toast'
import Dashboard from './screens/Dashboard'
import Games from './screens/Games'
import SetupWizard from './screens/SetupWizard'
import Landing from './screens/Landing'
import './index.css'

function AppShell() {
  useMe()

  const { user, ready } = useAuthStore()
  const [tab, setTab]             = useState('dashboard')
  const [targetGameId, setTargetGameId] = useState(null)
  const [drawer, setDrawer]       = useState(false)
  const [drawerTab, setDrawerTab] = useState(null)

  function openDrawer(initialTab) {
    setDrawerTab(initialTab ?? null)
    setDrawer(true)
  }

  if (!ready) return <div className="empty" style={{marginTop:80}}>Loading…</div>

  if (!user) {
    return <Landing />
  }

  if (!user.setup_done) {
    return <SetupWizard user={user} />
  }

  const subscribed = user.subscription_valid !== false

  return (
    <>
      <TickerStrip />
      <MainNav activeTab={tab} onTabChange={t => { if (t === 'games') setTargetGameId(null); setTab(t) }} onOpenDrawer={openDrawer} subscribed={subscribed} />
      <SettingsDrawer open={drawer} onClose={() => setDrawer(false)} initialTab={drawerTab} />

      {tab === 'dashboard' && <Dashboard openDrawer={openDrawer} subscribed={subscribed} onGoGames={(id) => { setTargetGameId(id ?? null); setTab('games') }} />}
      {tab === 'games'     && <Games subscribed={subscribed} initialGameId={targetGameId} />}
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
