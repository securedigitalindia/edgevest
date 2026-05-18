import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listRecs, createRec, deleteRec, exitRec, pushRec, listTrades, exitTrade } from '../api/trades'

export function useRecs(status = 'open') {
  return useQuery({ queryKey: ['recs', status], queryFn: () => listRecs(status), refetchInterval: 10000 })
}

export function useCreateRec() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createRec,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['recs'] }),
  })
}

export function useDeleteRec() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteRec,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['recs'] }),
  })
}

export function useExitRec(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => exitRec(id, data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['recs'] }),
  })
}

export function usePushRec(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => pushRec(id, data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['recs'] }); qc.invalidateQueries({ queryKey: ['trades'] }) },
  })
}

export function useTrades(params) {
  return useQuery({ queryKey: ['trades', params], queryFn: () => listTrades(params), refetchInterval: 10000 })
}

export function useExitTrade(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => exitTrade(id, data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['trades'] }),
  })
}
