import { useEffect, useRef } from 'react'
import { fetchPrices } from '../api/trades'
import usePriceStore from '../store/priceStore'

const POLL_MS = 5000

export default function usePrices() {
  const setSpot  = usePriceStore(s => s.setSpot)
  const timerRef = useRef(null)

  useEffect(() => {
    async function poll() {
      try {
        const data = await fetchPrices([])
        setSpot(data._spot || {}, false)
      } catch {
        setSpot({}, true)
      }
    }
    poll()
    timerRef.current = setInterval(poll, POLL_MS)
    return () => clearInterval(timerRef.current)
  }, [setSpot])
}
