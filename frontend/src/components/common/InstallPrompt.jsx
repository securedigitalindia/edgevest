import { useState } from 'react'
import useInstallPrompt from '../../hooks/useInstallPrompt'
import { CloseIcon } from './Icons'
import './InstallPrompt.css'

const DISMISS_KEY = 'edgevest_install_prompt_dismissed'

function wasDismissed() {
  try { return localStorage.getItem(DISMISS_KEY) === '1' } catch { return false }
}

function persistDismiss() {
  try { localStorage.setItem(DISMISS_KEY, '1') } catch { /* private mode etc. — fine to just not persist */ }
}

export default function InstallPrompt() {
  const { canInstall, promptInstall } = useInstallPrompt()
  const [dismissed, setDismissed] = useState(wasDismissed)

  if (!canInstall || dismissed) return null

  function dismiss() {
    persistDismiss()
    setDismissed(true)
  }

  return (
    <div className="install-prompt">
      <span>Install EdgeVest for quick access and a native-app feel</span>
      <div className="install-prompt-actions">
        <button className="btn btn-primary btn-sm" onClick={promptInstall}>Install</button>
        <button className="install-prompt-dismiss" onClick={dismiss} aria-label="Dismiss"><CloseIcon size={11}/></button>
      </div>
    </div>
  )
}
