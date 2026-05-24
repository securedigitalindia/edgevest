import { Component } from 'react'

export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: '40px 24px', textAlign: 'center', maxWidth: 480, margin: '80px auto' }}>
          <div style={{ fontSize: 36, marginBottom: 16 }}>⚠️</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>Something went wrong</div>
          <div style={{ fontSize: 13, color: '#64748b', marginBottom: 24 }}>{this.state.error.message}</div>
          <button
            onClick={() => window.location.reload()}
            style={{ padding: '8px 20px', borderRadius: 8, background: '#3b82f6', color: '#fff', border: 'none', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}
          >
            Reload page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
