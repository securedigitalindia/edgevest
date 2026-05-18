import { create } from 'zustand'

const usePriceStore = create(set => ({
  spot:    {},   // { NIFTY50: { ltp, change }, ... }
  stale:   true,
  setSpot: (spot, stale = false) => set({ spot, stale }),
}))

export default usePriceStore
