import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listRecs, createRec, deleteRec, exitRec, adjustRec, createAccountTrade,
  listTrades, listHistory, exitTrade, applyAdjTrade, deleteTrade,
  listBrokers, addBroker, listAccounts, addAccount, fetchPrices,
  updateAccountCapital, getAccountPortfolio,
} from '../api/trades'

export function useRecs() {
  return useQuery({ queryKey: ['recs'], queryFn: listRecs, refetchInterval: 10000 })
}

export function useRecPrices(keys = []) {
  const keyStr = [...keys].sort().join(',')
  return useQuery({
    queryKey: ['rec-prices', keyStr],
    queryFn:  () => fetchPrices(keys),
    enabled:  keys.length > 0,
    refetchInterval: 5000,
    staleTime: 4000,
  })
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

export function useAdjustRec(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => adjustRec(id, data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['recs'] }),
  })
}

export function useCreateAccountTrade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createAccountTrade,
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['recs'] }); qc.invalidateQueries({ queryKey: ['trades'] }) },
  })
}

export function useTrades(params) {
  return useQuery({ queryKey: ['trades', params], queryFn: () => listTrades(params), refetchInterval: 10000 })
}

export function useTradeHistory(params, enabled = true) {
  return useQuery({
    queryKey: ['trade-history', params],
    queryFn:  () => listHistory(params),
    enabled,
  })
}

export function useExitTrade(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => exitTrade(id, data),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ['trades'] })
      qc.invalidateQueries({ queryKey: ['trade-history'] })
    },
  })
}

export function useApplyAdjTrade(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => applyAdjTrade(id, data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['trades'] }),
  })
}

export function useDeleteTrade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteTrade,
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ['trades'] })
      qc.invalidateQueries({ queryKey: ['trade-history'] })
    },
  })
}

export function useBrokers() {
  return useQuery({ queryKey: ['brokers'], queryFn: listBrokers })
}

export function useAccounts() {
  return useQuery({ queryKey: ['accounts'], queryFn: listAccounts })
}

export function useAddBroker() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: addBroker,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['brokers'] }),
  })
}

export function useAddAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: addAccount,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  })
}

export function useUpdateAccountCapital(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: data => updateAccountCapital(id, data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['accounts'] }); qc.invalidateQueries({ queryKey: ['acct-portfolio', id] }) },
  })
}

export function useAccountPortfolio(id) {
  return useQuery({
    queryKey:        ['acct-portfolio', id],
    queryFn:         () => getAccountPortfolio(id),
    enabled:         !!id,
    refetchInterval: 10000,
  })
}
