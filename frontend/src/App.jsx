import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import useAuthStore from './store/authStore'
import useMe from './hooks/useMe'
import TickerStrip from './components/nav/TickerStrip'
import MainNav from './components/nav/MainNav'
import { ToastProvider } from './components/common/Toast'
import OfflineBanner from './components/common/OfflineBanner'
import InstallPrompt from './components/common/InstallPrompt'
import './index.css'
// Tailwind + shadcn/ui — scoped to .sc-scope, inert on every existing page.
// See src/styles/shadcn.css's header comment for why.
import './styles/shadcn.css'

// Route-level code splitting — each of these is only needed for one of the
// mutually-exclusive states below (logged out / mid-setup / main app), or
// only once the user actually navigates to that particular page, so none of
// them need to ship in the initial bundle for every visit.
const Dashboard       = lazy(() => import('./screens/Dashboard'))
const Trades          = lazy(() => import('./screens/Trades'))
const Positions       = lazy(() => import('./screens/Positions'))
const Games           = lazy(() => import('./screens/Games'))
const SetupWizard     = lazy(() => import('./screens/SetupWizard'))
const Landing         = lazy(() => import('./screens/Landing'))
const ProfileHub      = lazy(() => import('./screens/profile/ProfileHub'))
const ProfileDetails  = lazy(() => import('./screens/profile/ProfileDetails'))
const MyPlan          = lazy(() => import('./screens/profile/MyPlan'))
const MyAccounts      = lazy(() => import('./screens/profile/MyAccounts'))
const Gems            = lazy(() => import('./screens/profile/Gems'))
const Referrals       = lazy(() => import('./screens/profile/Referrals'))
const Brokers         = lazy(() => import('./screens/profile/Brokers'))
const Users           = lazy(() => import('./screens/profile/Users'))
const Plans           = lazy(() => import('./screens/profile/Plans'))
const Subscriptions   = lazy(() => import('./screens/profile/Subscriptions'))
const Reports         = lazy(() => import('./screens/profile/Reports'))
const Learn           = lazy(() => import('./screens/profile/Learn'))
const LearnArticle    = lazy(() => import('./screens/profile/LearnArticle'))

const Loading = () => <div className="empty" style={{marginTop:80}}>Loading…</div>

function RootRedirect() {
  const { search } = useLocation()
  return <Navigate to={`/dashboard${search}`} replace />
}

function AppShell() {
  useMe()

  const { user, ready } = useAuthStore()

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
      <MainNav subscribed={subscribed} />
      <InstallPrompt />
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/"                     element={<RootRedirect />} />
          <Route path="/dashboard"             element={<Dashboard />} />
          <Route path="/trades"                element={<Trades subscribed={subscribed} />} />
          <Route path="/positions"             element={<Positions />} />
          <Route path="/games"                 element={<Games subscribed={subscribed} />} />
          <Route path="/games/:id"             element={<Games subscribed={subscribed} />} />
          <Route path="/profile"               element={<ProfileHub />} />
          <Route path="/profile/details"       element={<ProfileDetails />} />
          <Route path="/profile/plan"          element={<MyPlan />} />
          <Route path="/profile/accounts"      element={<MyAccounts />} />
          <Route path="/profile/gems"          element={<Gems />} />
          <Route path="/profile/referrals"     element={<Referrals />} />
          <Route path="/profile/brokers"       element={<Brokers />} />
          <Route path="/profile/users"         element={<Users />} />
          <Route path="/profile/plans"         element={<Plans />} />
          <Route path="/profile/subscriptions" element={<Subscriptions />} />
          <Route path="/profile/reports"       element={<Reports />} />
          <Route path="/profile/learn"         element={<Learn />} />
          <Route path="/profile/learn/:slug"   element={<LearnArticle />} />
          <Route path="*"                      element={<Navigate to="/dashboard" replace />} />
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
