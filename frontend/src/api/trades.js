import api from './client'

export const listRecs       = (status='open')=> api.get(`/recommendations?status=${status}`).then(r => r.data)
export const createRec      = data           => api.post('/recommendations', data).then(r => r.data)
export const deleteRec      = id             => api.delete(`/recommendations/${id}`).then(r => r.data)
export const exitRec        = (id, data)     => api.post(`/recommendations/${id}/exit`, data).then(r => r.data)
export const pushRec        = (id, data)     => api.post(`/recommendations/${id}/push`, data).then(r => r.data)
export const listTrades     = params         => api.get('/trades', { params }).then(r => r.data)
export const exitTrade      = (id, data)     => api.post(`/trades/${id}/exit`, data).then(r => r.data)
export const listBrokers    = ()             => api.get('/brokers').then(r => r.data)
export const addBroker      = data           => api.post('/brokers', data).then(r => r.data)
export const listAccounts   = ()             => api.get('/accounts').then(r => r.data)
export const addAccount     = data           => api.post('/accounts', data).then(r => r.data)
export const searchInstruments = q          => api.get(`/instruments/search?q=${encodeURIComponent(q)}`).then(r => r.data)
