import { useEffect, useId, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPrices } from '../api/trades'
import usePriceKeysStore from '../store/priceKeysStore'

function useUnionKeys() {
  // Select the raw, Zustand-stable object first — computing the derived
  // array inside the selector itself would return a new reference on every
  // call and break useSyncExternalStore's snapshot caching (infinite loop).
  const keySets = usePriceKeysStore(state => state.keySets)
  return useMemo(() => {
    const all = new Set()
    for (const keys of Object.values(keySets)) keys.forEach(k => all.add(k))
    return [...all].sort()
  }, [keySets])
}

// One shared poll backs every price consumer in the app (TickerStrip,
// Dashboard, GameDetail). All of them build the exact same queryKey (the
// union of every mounted consumer's needed instrument keys, tracked via
// priceKeysStore), so TanStack Query dedupes them into a single request
// instead of each one independently hitting /api/prices every 5s.
function useSharedPricesQuery() {
  const keys   = useUnionKeys()
  const keyStr = keys.join(',')
  return useQuery({
    queryKey:        ['prices', keyStr],
    queryFn:         () => fetchPrices(keys),
    refetchInterval: 5000,
    staleTime:       4000,
  })
}

export default function usePrices() {
  const { data, ...rest } = useSharedPricesQuery()
  return { ...rest, data: data ? { spot: data._spot || {}, stale: !data._ts } : undefined }
}

// For consumers that need specific instrument keys (not just spot prices) —
// declares the keys this component needs and returns the raw shared
// response, so callers can index into it directly (e.g. prices[instrKey]).
export function useTrackedPrices(keys = []) {
  const id        = useId()
  const setKeys   = usePriceKeysStore(s => s.setKeys)
  const clearKeys = usePriceKeysStore(s => s.clearKeys)
  const keyStr    = [...keys].sort().join(',')

  useEffect(() => {
    setKeys(id, keyStr ? keyStr.split(',') : [])
    return () => clearKeys(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, keyStr])

  return useSharedPricesQuery()
}
