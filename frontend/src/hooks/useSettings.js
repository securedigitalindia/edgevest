import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listUsers, saveUserProfile, changeUserRole, listPlans, createPlan, togglePlan, listSubs } from '../api/settings'

export function useUsers() {
  return useQuery({ queryKey: ['users'], queryFn: listUsers })
}

export function useSaveUserProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ uid, ...data }) => saveUserProfile(uid, data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useChangeUserRole() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ uid, role }) => changeUserRole(uid, role),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function usePlans() {
  return useQuery({ queryKey: ['plans'], queryFn: listPlans })
}

export function useCreatePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createPlan,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['plans'] }),
  })
}

export function useTogglePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, active }) => togglePlan(id, active),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['plans'] }),
  })
}

export function useSubs() {
  return useQuery({ queryKey: ['subs'], queryFn: listSubs })
}
