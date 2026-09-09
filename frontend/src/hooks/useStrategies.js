import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listStrategies, getStrategyConfig, setStrategyConfig, runStrategy } from '../api/strategies'

export function useStrategies() {
  return useQuery({ queryKey: ['strategies'], queryFn: listStrategies })
}

export function useStrategyConfig(id) {
  return useQuery({
    queryKey: ['strategy-config', id],
    queryFn: () => getStrategyConfig(id),
    enabled: !!id,
  })
}

export function useSetStrategyConfig(id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: payload => setStrategyConfig(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategy-config', id] })
      qc.invalidateQueries({ queryKey: ['strategy-run', id] })
    },
  })
}

// Polls the same ~1-minute cadence the PRD specifies — the caching design on
// the backend (settle-once per bounded window) keeps this affordable even
// though it's faster than the underlying ~5-min data capture cadence.
//
// configVersion (2026-09-09): the confirmed config's own confirmed_at —
// folded into the query key specifically so a reconfigure produces a
// genuinely NEW key. Without this, TanStack Query sees the "same" query
// (same id, same end_date) after a reconfigure and shows the OLD result
// while silently refetching in the background — confusing here, since the
// old numbers were computed under the previous params and don't represent
// what's about to load. With a new key, the transition is a real
// `isLoading` (no stale data shown at all) rather than a stale-then-swap.
export function useStrategyRun(id, { enabled = true, end_date, configVersion } = {}) {
  return useQuery({
    queryKey: ['strategy-run', id, end_date || null, configVersion || null],
    queryFn: () => runStrategy(id, end_date ? { end_date } : {}),
    enabled: !!id && enabled,
    refetchInterval: 60_000,
  })
}
