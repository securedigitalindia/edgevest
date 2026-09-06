// Copy text to the clipboard with a legacy fallback — navigator.clipboard.
// writeText() throws NotAllowedError whenever the document isn't focused at
// the exact call moment (devtools, another window had focus a beat earlier),
// which execCommand('copy') tolerates. Same tested fallback chain as
// screens/profile/Referrals.jsx's copyLink(); kept as a shared util instead
// of duplicated so a second call site (Trades.jsx's position Share button)
// doesn't drift from it. Returns true/false — callers show their own toast.
export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // fall through to the legacy fallback below
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}
