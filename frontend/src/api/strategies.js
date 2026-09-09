import api from './client'

// Admin-only "Strategies" dashboard — see docs/prd/admin-strategies-dashboard.md.
export const listStrategies      = ()               => api.get('/strategies').then(r => r.data)
export const getStrategyConfig   = id                => api.get(`/strategies/${id}/config`).then(r => r.data)
export const setStrategyConfig   = (id, payload)     => api.post(`/strategies/${id}/config`, payload).then(r => r.data)
export const runStrategy         = (id, params = {}) => api.get(`/strategies/${id}/run`, { params }).then(r => r.data)
