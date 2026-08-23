import useOnlineStatus from '../../hooks/useOnlineStatus'
import './OfflineBanner.css'

export default function OfflineBanner() {
  const online = useOnlineStatus()
  if (online) return null
  return (
    <div className="offline-banner" role="status">
      You&rsquo;re offline — prices and data shown may be stale
    </div>
  )
}
