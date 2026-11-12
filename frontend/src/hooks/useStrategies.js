import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listStrategies, getStrategyConfig, setStrategyConfig, runStrategy, getDayList, getDay } from '../api/strategies'

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
    // Returned promise is awaited by react-query before the caller's own
    // mutate({ onSuccess }) runs — so the form only closes once the NEW config
    // is in the cache. Without the await, the detail view re-rendered
    // immediately with the previous config (old input chips + the old
    // config's cached results) and only swapped to the new ones when the
    // refetch landed. Old run results are dropped outright (not refetched):
    // their query key embeds the old config's confirmed_at, so nothing will
    // ever read them again.
    onSuccess: async () => {
      qc.removeQueries({ queryKey: ['strategy-run', id] })
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['strategy-config', id] }),
        qc.invalidateQueries({ queryKey: ['strategies'] }),
      ])
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

// Day view: the day list refreshes every minute (a new day / a new touch appears as the poller captures the chain);
// one day's payload refreshes every minute only while it is the live (newest) day.
export function useDayList(id) {
  return useQuery({ queryKey: ['strategy-days', id], queryFn: () => getDayList(id), enabled: !!id, refetchInterval: 60_000 })
}

export function useDay(id, date, variant, live) {
  return useQuery({
    queryKey: ['strategy-day', id, date, variant],
    queryFn: () => getDay(id, date, variant),
    enabled: !!id && !!date && !!variant,
    refetchInterval: live ? 60_000 : false,
    staleTime: live ? 30_000 : 10 * 60_000,
    placeholderData: prev => prev,     // keep the previous chart on screen while the next day loads
  })
}
