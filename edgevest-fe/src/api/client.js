import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
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
