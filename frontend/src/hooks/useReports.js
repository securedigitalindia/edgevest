import { useQuery } from '@tanstack/react-query'
import { getMonthlyReport } from '../api/reports'

export function useMonthlyReport(month) {
  return useQuery({
    queryKey: ['monthly-report', month],
    queryFn:  () => getMonthlyReport(month),
  })
}
