import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getMe } from '../api/auth'
import useAuthStore from '../store/authStore'

export default function useMe() {
  const { setUser, clear } = useAuthStore()
  const { data, isError } = useQuery({
    queryKey: ['me'],
    queryFn:  getMe,
    retry:    false,
    staleTime: Infinity,
  })

  useEffect(() => {
    if (data)    setUser(data)
    if (isError) clear()
  }, [data, isError, setUser, clear])
}
