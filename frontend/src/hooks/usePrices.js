import { useQuery } from '@tanstack/react-query'
import { fetchPrices } from '../api/trades'

export default function usePrices() {
  return useQuery({
    queryKey:        ['spot-prices'],
    queryFn:         () => fetchPrices([]),
    refetchInterval: 5000,
    staleTime:       4000,
    select:          data => ({ spot: data._spot || {}, stale: !data._ts }),
  })
}
