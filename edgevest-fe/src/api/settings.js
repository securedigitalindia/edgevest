import api from './client'

export const listUsers        = ()                  => api.get('/users').then(r => r.data.users)
export const saveUserProfile  = (uid, data)         => api.post(`/users/${uid}/profile`, data).then(r => r.data)
export const changeUserRole   = (uid, role)         => api.post(`/users/${uid}/role`, { role }).then(r => r.data)
export const getProfile       = ()                  => api.get('/profile').then(r => r.data.profile)
export const saveProfile      = data                => api.post('/profile', data).then(r => r.data)
export const listPlans      = ()            => api.get('/plans').then(r => r.data.plans)
export const createPlan     = data          => api.post('/plans', data).then(r => r.data)
export const updatePlan     = (id, data)    => api.put(`/plans/${id}`, data).then(r => r.data)
export const togglePlan     = (id, active)  => api.post(`/plans/${id}/toggle`, { active }).then(r => r.data)
export const listSubs       = ()            => api.get('/subscriptions').then(r => r.data.subscriptions)
