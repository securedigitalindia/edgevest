import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listGames, getGame, submitEntry, resolveGame, createGame, updateGame,
         deleteGame, activateGame, closeGame, reopenGame, getPortfolio, submitVirtualTrade } from '../api/games'

export function useGames() {
  return useQuery({ queryKey: ['games'], queryFn: listGames, refetchInterval: 30000 })
}

export function useGame(id) {
  return useQuery({ queryKey: ['game', id], queryFn: () => getGame(id), enabled: !!id, refetchInterval: 10000 })
}

export function usePortfolio(id) {
  return useQuery({ queryKey: ['portfolio', id], queryFn: () => getPortfolio(id), enabled: !!id, refetchInterval: 10000 })
}

export function useSubmitEntry(gid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => submitEntry(gid, data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['game', gid] }); qc.invalidateQueries({ queryKey: ['games'] }) },
  })
}

export function useSubmitVirtualTrade(gid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => submitVirtualTrade(gid, data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['portfolio', gid] }),
  })
}

export function useResolveGame(gid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => resolveGame(gid, data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['game', gid] }); qc.invalidateQueries({ queryKey: ['games'] }) },
  })
}

export function useActivateGame(gid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => activateGame(gid),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['game', gid] }); qc.invalidateQueries({ queryKey: ['games'] }) },
  })
}

export function useCloseGame(gid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => closeGame(gid),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['game', gid] }); qc.invalidateQueries({ queryKey: ['games'] }) },
  })
}

export function useReopenGame(gid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => reopenGame(gid),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['game', gid] }); qc.invalidateQueries({ queryKey: ['games'] }) },
  })
}

export function useCreateGame() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createGame,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['games'] }),
  })
}

export function useUpdateGame(gid) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => updateGame(gid, data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['game', gid] }); qc.invalidateQueries({ queryKey: ['games'] }) },
  })
}

export function useDeleteGame() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteGame,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['games'] }),
  })
}
