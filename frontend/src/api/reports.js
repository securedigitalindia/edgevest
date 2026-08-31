import api from './client'

// Admin-only monthly recommendation report — one round trip returns every
// metric the Reports screen needs (positions entered, margin series/peak,
// P&L events/total). `month` is `YYYY-MM` (IST calendar month); omitted =
// backend defaults to the current IST month.
export const getMonthlyReport = month =>
  api.get('/reports/monthly', { params: month ? { month } : {} }).then(r => r.data)
