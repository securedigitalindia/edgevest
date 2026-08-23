import { useState, Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import useAuthStore from './store/authStore'
import useMe from './hooks/useMe'
import TickerStrip from './components/nav/TickerStrip'
import MainNav from './components/nav/MainNav'
import { ToastProvider } from './components/common/Toast'
import OfflineBanner from './components/common/OfflineBanner'
import InstallPrompt from './components/common/InstallPrompt'
import './index.css'

// Route-level code splitting — each of these is only needed for one of the
// mutually-exclusive states below (logged out / mid-setup / main app), or
// (SettingsDrawer) only once the user actually opens it, so none of them
// need to ship in the initial bundle for every visit.
const Dashboard      = lazy(() => import('./screens/Dashboard'))
const Games          = lazy(() => import('./screens/Games'))
const SetupWizard    = lazy(() => import('./screens/SetupWizard'))
const Landing        = lazy(() => import('./screens/Landing'))
const SettingsDrawer = lazy(() => import('./components/drawer/SettingsDrawer'))

const Loading = () => <div className="empty" style={{marginTop:80}}>Loading…</div>

function RootRedirect() {
  const { search } = useLocation()
  return <Navigate to={`/dashboard${search}`} replace />
}

function AppShell() {
  useMe()

  const { user, ready } = useAuthStore()
  const [drawer, setDrawer]             = useState(false)
  const [drawerTab, setDrawerTab]       = useState(null)
  // Stays true once the drawer's been opened the first time, so its chunk is
  // still only fetched on demand, but it stays mounted afterwards — needed
  // for its open/close CSS transition to actually play (unmounting on every
  // close would just make it vanish instantly instead of sliding out).
  const [drawerLoaded, setDrawerLoaded] = useState(false)

  function openDrawer(initialTab) {
    setDrawerTab(initialTab ?? null)
    setDrawer(true)
    setDrawerLoaded(true)
  }

  if (!ready) return <Loading />

  if (!user) {
    return <Suspense fallback={<Loading />}><Routes><Route path="*" element={<Landing />} /></Routes></Suspense>
  }

  if (!user.setup_done) {
    return <Suspense fallback={<Loading />}><Routes><Route path="*" element={<SetupWizard user={user} />} /></Routes></Suspense>
  }

  const subscribed = user.subscription_valid !== false

  return (
    <>
      <OfflineBanner />
      <TickerStrip />
      <MainNav onOpenDrawer={openDrawer} subscribed={subscribed} />
      <InstallPrompt />
      {drawerLoaded && (
        <Suspense fallback={null}>
          <SettingsDrawer open={drawer} onClose={() => setDrawer(false)} initialTab={drawerTab} />
        </Suspense>
      )}
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/"          element={<RootRedirect />} />
          <Route path="/dashboard" element={<Dashboard openDrawer={openDrawer} subscribed={subscribed} />} />
          <Route path="/games"     element={<Games subscribed={subscribed} />} />
          <Route path="/games/:id" element={<Games subscribed={subscribed} />} />
          <Route path="*"          element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
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
