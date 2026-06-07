import axios from 'axios'

export const API_BASE  = import.meta.env.VITE_API_URL || '/api'
export const AUTH_BASE = API_BASE.replace(/\/api$/, '')

const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
})

api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      // Session expired — clear state and go to root so Landing renders
      window.location.href = '/'
      return new Promise(() => {})  // never resolve — page is reloading
    }
    const msg = err.response?.data?.error || err.message || 'Request failed'
    return Promise.resolve({ data: { ok: false, error: msg } })
  }
)

export default api
