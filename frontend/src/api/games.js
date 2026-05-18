import api from './client'

export const listGames  = ()        => api.get('/games').then(r => r.data.games)
export const getGame    = id        => api.get(`/games/${id}`).then(r => r.data.game)
export const createGame = data      => api.post('/games', data).then(r => r.data)
export const updateGame = (id, data)=> api.patch(`/games/${id}`, data).then(r => r.data)
export const deleteGame = id        => api.delete(`/games/${id}`).then(r => r.data)
export const submitEntry= (id, data)=> api.post(`/games/${id}/entry`, data).then(r => r.data)
export const resolveGame= (id, data)=> api.post(`/games/${id}/resolve`, data).then(r => r.data)
export const getCredits = ()        => api.get('/credits').then(r => r.data)
