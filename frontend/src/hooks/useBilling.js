import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { createOrder, verifyPayment, getMySubscription } from '../api/billing'

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
