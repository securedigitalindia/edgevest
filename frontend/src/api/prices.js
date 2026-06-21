import api from './client'

export const getSpotPrices = () => api.get('/spot').then(r => r.data)
