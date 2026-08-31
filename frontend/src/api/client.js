import axios from 'axios'

export const API_BASE  = import.meta.env.VITE_API_URL || '/api'
export const AUTH_BASE = API_BASE.replace(/\/api$/, '')

// One backend can be reached from multiple frontend origins (e.g. dev's Vite
// server AND its CloudFront bundle) — tell it where to redirect back to after
// login/logout instead of relying on the backend's single static FRONTEND_URL.
// `extra` carries any additional query params (e.g. `{ ref }` for referral
// links) alongside the always-present `next`.
export const authUrl = (path, extra = {}) => {
  const params = new URLSearchParams({ next: window.location.origin })
  for (const [k, v] of Object.entries(extra)) {
    if (v != null && v !== '') params.set(k, v)
  }
  return `${AUTH_BASE}${path}?${params.toString()}`
}

const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
})

api.interceptors.response.use(
  res => res,
  err => {
    const msg = err.response?.data?.error || err.message || 'Request failed'
    return Promise.resolve({ data: { ok: false, error: msg } })
  }
)

export default api
