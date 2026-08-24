import { useNavigate, useLocation } from 'react-router-dom'
import './PageHeader.css'

// Shared title bar for standalone pages, with an optional back-button.
// `back` is an optional explicit path; default behavior is `navigate(-1)` with a
// fallback to `fallback` (used when there's no history entry to go back to, e.g.
// a bookmarked/deep-linked page load). Pass `showBack={false}` for a page that's
// a primary nav destination rather than a drill-down (e.g. Positions) — hardware/
// browser back already does the right thing there without an explicit affordance.
export default function PageHeader({ title, back, fallback = '/dashboard', showBack = true }) {
  const navigate = useNavigate()
  const location = useLocation()

  function goBack() {
    if (back) { navigate(back); return }
    // location.key is 'default' only for the very first history entry this
    // browser session ever had (React Router's own sentinel for "nothing to
    // pop back to in this app") — window.history.length counts the whole
    // browser session's history, including entries from before the app was
    // ever opened (a PWA relaunch, a prior tab), so it can read > 2 even on
    // a cold deep link with no real in-app page behind it, sending
    // navigate(-1) out of the app instead of to `fallback`.
    if (location.key !== 'default') navigate(-1)
    else navigate(fallback)
  }

  return (
    <div className="page-header">
      {showBack && (
        <button className="page-header-back" onClick={goBack} aria-label="Back">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M11 3.5L5.5 9l5.5 5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      )}
      <h1 className="page-header-title">{title}</h1>
    </div>
  )
}
