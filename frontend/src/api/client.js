import axios from 'axios'

const api = axios.create({ baseURL: '/api', withCredentials: true })

api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) window.location.href = '/auth/google'
    // Resolve with error payload so callers can do `if (res.ok)` without try/catch
    const msg = err.response?.data?.error || err.message || 'Request failed'
    return Promise.resolve({ data: { ok: false, error: msg } })
  }
)

export default api
