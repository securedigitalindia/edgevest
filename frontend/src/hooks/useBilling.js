import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createOrder, verifyPayment } from '../api/billing'

export function useCreateOrder() {
  return useMutation({ mutationFn: createOrder })
}

export function useVerifyPayment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: verifyPayment,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
}
