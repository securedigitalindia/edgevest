import { create } from 'zustand'

const useAuthStore = create(set => ({
  user:    null,
  ready:   false,
  setUser: user  => set({ user, ready: true }),
  clear:   ()    => set({ user: null, ready: true }),
}))

export default useAuthStore
