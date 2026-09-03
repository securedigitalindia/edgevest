import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { createOrder, verifyPayment, getMySubscription, listPayments, reconcilePayment } from '../api/billing'

export function useCreateOrder() {
  return useMutation({ mutationFn: createOrder })
}

export function useVerifyPayment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: verifyPayment,
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ['me'] })
      qc.invalidateQueries({ queryKey: ['my-subscription'] })
    },
  })
}

export function useMySubscription() {
  return useQuery({ queryKey: ['my-subscription'], queryFn: getMySubscription })
}

export function usePayments() {
  return useQuery({ queryKey: ['payments'], queryFn: listPayments })
}

export function useReconcilePayment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: reconcilePayment,
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ['payments'] })
      // A reconcile can activate a subscription (or leave one refunded)
      // behind the scenes — keep the other admin views in sync too.
      qc.invalidateQueries({ queryKey: ['users'] })
      qc.invalidateQueries({ queryKey: ['subs'] })
    },
  })
}
