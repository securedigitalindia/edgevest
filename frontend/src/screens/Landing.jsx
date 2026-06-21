import { AUTH_BASE } from '../api/client'

const GOOGLE_SVG = (
  <svg viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" style={{width:18,height:18,flexShrink:0}}>
    <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z" fill="#4285F4"/>
    <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z" fill="#34A853"/>
    <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z" fill="#FBBC05"/>
    <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58Z" fill="#EA4335"/>
  </svg>
)

export default function Landing() {
  return (
    <div style={{background:'#fff',minHeight:'100vh',color:'#0f172a',fontFamily:'-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'}}>

      {/* Nav */}
      <nav style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'0 40px',height:56,borderBottom:'1px solid #f1f5f9'}}>
        <div style={{fontSize:17,fontWeight:800,letterSpacing:'-.3px',color:'#0f172a'}}>
          Edge<span style={{color:'#3b82f6'}}>Vest</span>
        </div>
        <a href={`${AUTH_BASE}/auth/google`} style={{display:'inline-flex',alignItems:'center',gap:8,background:'#0f172a',color:'#fff',border:'none',borderRadius:8,padding:'8px 18px',fontSize:13,fontWeight:600,cursor:'pointer',textDecoration:'none'}}>
          {GOOGLE_SVG}
          Sign in with Google
        </a>
      </nav>

      {/* Hero */}
      <section style={{maxWidth:720,margin:'0 auto',padding:'80px 24px 64px',textAlign:'center'}}>
        <div style={{display:'inline-flex',alignItems:'center',gap:6,background:'#eff6ff',color:'#1d4ed8',borderRadius:20,padding:'4px 12px',fontSize:12,fontWeight:600,letterSpacing:'.3px',marginBottom:24}}>
          <span style={{width:6,height:6,borderRadius:'50%',background:'#3b82f6',display:'inline-block'}} />
          Advisory-First
        </div>
        <h1 style={{fontSize:'clamp(32px,5vw,48px)',fontWeight:800,lineHeight:1.15,letterSpacing:'-.5px',color:'#0f172a',marginBottom:16}}>
          Stock market intelligence<br />built for <span style={{color:'#3b82f6'}}>serious traders</span>
        </h1>
        <p style={{fontSize:17,color:'#64748b',lineHeight:1.6,maxWidth:520,margin:'0 auto 36px'}}>
          Live F&O signals, Supertrend &amp; EMA alerts, trade tracking, and advisor-grade
          portfolio tools — all in one clean interface.
        </p>
        <div style={{display:'flex',gap:12,justifyContent:'center',flexWrap:'wrap'}}>
          <a href={`${AUTH_BASE}/auth/google`} style={{display:'inline-flex',alignItems:'center',gap:10,background:'#fff',color:'#0f172a',border:'1.5px solid #e2e8f0',borderRadius:10,padding:'12px 24px',fontSize:14,fontWeight:600,cursor:'pointer',textDecoration:'none',boxShadow:'0 1px 4px rgba(0,0,0,.06)'}}>
            {GOOGLE_SVG}
            Continue with Google
          </a>
        </div>
        <p style={{fontSize:12,color:'#94a3b8',marginTop:14}}>By continuing you agree to our terms. Invite-only access.</p>
      </section>

      {/* Segments strip */}
      <div style={{background:'#f8fafc',borderTop:'1px solid #f1f5f9',borderBottom:'1px solid #f1f5f9',padding:'28px 40px',textAlign:'center'}}>
        <div style={{fontSize:11,fontWeight:700,letterSpacing:'.8px',textTransform:'uppercase',color:'#94a3b8',marginBottom:14}}>Supported segments</div>
        <div style={{display:'flex',gap:10,justifyContent:'center',flexWrap:'wrap'}}>
          {['Equity','Derivatives (F&O)','Commodities','Indices'].map(s => (
            <span key={s} style={{background:'#fff',border:'1px solid #e2e8f0',borderRadius:20,padding:'5px 14px',fontSize:13,fontWeight:600,color:'#334155'}}>{s}</span>
          ))}
        </div>
      </div>

      {/* Features */}
      <section style={{maxWidth:900,margin:'0 auto',padding:'48px 24px 80px',display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:16}}>
        {[
          {icon:'⚡',title:'Live Signals',desc:'Supertrend, EMA & RSI crossings detected every 5 seconds during market hours.'},
          {icon:'📊',title:'F&O Trade Tracking',desc:'Track open positions, entry/exit prices, lot sizes and real-time P&L across strategies.'},
          {icon:'🔔',title:'Telegram Alerts',desc:'Instant alerts with trade suggestions delivered to your Telegram the moment a signal fires.'},
          {icon:'🛡️',title:'Advisor Tools',desc:'Push trades to client accounts, track adjustments, and manage multi-leg strategies.'},
        ].map(f => (
          <div key={f.title} style={{background:'#f8fafc',border:'1px solid #f1f5f9',borderRadius:12,padding:20}}>
            <div style={{fontSize:22,marginBottom:10}}>{f.icon}</div>
            <div style={{fontSize:14,fontWeight:700,color:'#0f172a',marginBottom:5}}>{f.title}</div>
            <div style={{fontSize:13,color:'#64748b',lineHeight:1.5}}>{f.desc}</div>
          </div>
        ))}
      </section>

      {/* Footer */}
      <footer style={{textAlign:'center',padding:24,fontSize:12,color:'#94a3b8'}}>
        &copy; 2026 EdgeVest &nbsp;&middot;&nbsp; Advisory-first market intelligence &nbsp;&middot;&nbsp; NSE / BSE
      </footer>
    </div>
  )
}
