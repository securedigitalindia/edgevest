import api from './client'

export const createOrder      = plan_id => api.post('/billing/create-order', { plan_id }).then(r => r.data)
export const verifyPayment    = payload => api.post('/billing/verify-payment', payload).then(r => r.data)
export const getMySubscription = ()     => api.get('/my-subscription').then(r => r.data)

// Loaded on-demand rather than in index.html, so the PWA's initial
// load/precache isn't touched by a 3rd-party script most users won't need.
let _rzpLoading = null
export function loadRazorpayScript() {
  if (window.Razorpay) return Promise.resolve(true)
  if (_rzpLoading) return _rzpLoading
  _rzpLoading = new Promise(resolve => {
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload  = () => resolve(true)
    s.onerror = () => resolve(false)
    document.body.appendChild(s)
  })
  return _rzpLoading
}
