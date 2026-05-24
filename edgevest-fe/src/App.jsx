import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
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
  const [drawer, setDrawer]       = useState(false)
  const [drawerTab, setDrawerTab] = useState(null)

  function openDrawer(initialTab) {
    setDrawerTab(initialTab ?? null)
    setDrawer(true)
  }

  if (!ready) return <div className="empty" style={{marginTop:80}}>Loading…</div>

  if (!user) {
    return <Routes><Route path="*" element={<Landing />} /></Routes>
  }

  if (!user.setup_done) {
    return <Routes><Route path="*" element={<SetupWizard user={user} />} /></Routes>
  }

  const subscribed = user.subscription_valid !== false

  return (
    <>
      <TickerStrip />
      <MainNav onOpenDrawer={openDrawer} subscribed={subscribed} />
      <SettingsDrawer open={drawer} onClose={() => setDrawer(false)} initialTab={drawerTab} />
      <Routes>
        <Route path="/"          element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard openDrawer={openDrawer} subscribed={subscribed} />} />
        <Route path="/games"     element={<Games subscribed={subscribed} />} />
        <Route path="/games/:id" element={<Games subscribed={subscribed} />} />
        <Route path="*"          element={<Navigate to="/dashboard" replace />} />
      </Routes>
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
