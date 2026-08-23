import { create } from 'zustand'

// Tracks which extra instrument keys each currently-mounted price consumer
// needs, so usePrices() can poll the union of all of them in one shared
// request instead of each consumer polling /api/prices independently.
const usePriceKeysStore = create(set => ({
  keySets: {},
  setKeys:   (ownerId, keys) => set(state => ({ keySets: { ...state.keySets, [ownerId]: keys } })),
  clearKeys: (ownerId)       => set(state => {
    const keySets = { ...state.keySets }
    delete keySets[ownerId]
    return { keySets }
  }),
}))

export default usePriceKeysStore
