import { useQuery } from '@tanstack/react-query'
import { getCredits } from '../../api/games'
import PageHeader from '../../components/common/PageHeader'
import { fmtIstShort } from '../../utils/format'
import './Profile.css'

const REASON_LABEL = {
  game_win:               '🏆 Game win',
  game_reward:            '🎮 Game reward',
  subscription_purchase:  '🔓 Subscription',
  manual:                 '⚙️ Manual',
  refund:                 '↩️ Refund',
}

export default function Gems() {
  const { data, isLoading } = useQuery({ queryKey: ['credits'], queryFn: getCredits, refetchInterval: 30000 })
  const balance = data?.balance ?? 0
  const history = data?.history ?? []

  return (
    <div className="profile-page">
      <PageHeader title="Gems" fallback="/profile" />
      <div className="stab-panel active">
        {/* Balance card */}
        <div style={{background:'linear-gradient(135deg,#1e1b4b,#312e81)',borderRadius:10,padding:'16px 18px',marginBottom:16,display:'flex',alignItems:'center',justifyContent:'space-between'}}>
          <div>
            <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.6,color:'#a5b4fc',marginBottom:4}}>Gem Balance</div>
            <div style={{fontSize:28,fontWeight:800,color:'#fbbf24'}}>💎 {balance}</div>
          </div>
          <div style={{fontSize:11,color:'#818cf8',textAlign:'right',lineHeight:1.6}}>
            Earn by winning<br/>games &amp; quizzes.<br/>Spend on plans.
          </div>
        </div>

        {/* History */}
        <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:.5,color:'var(--muted)',marginBottom:8}}>Transaction History</div>
        {isLoading && <div className="empty">Loading…</div>}
        {!isLoading && !history.length && <div className="empty">No transactions yet. Play a game to earn your first gems!</div>}
        {history.map(tx => (
          <div key={tx.id} style={{display:'flex',alignItems:'center',gap:10,padding:'9px 0',borderBottom:'1px solid #f1f5f9'}}>
            <div style={{flex:1,minWidth:0}}>
              <div style={{fontSize:13,fontWeight:600,color:'#1e293b'}}>
                {REASON_LABEL[tx.reason] || tx.reason}
                {tx.note ? <span style={{fontWeight:400,color:'var(--muted)'}}> · {tx.note}</span> : null}
              </div>
              <div style={{fontSize:11,color:'var(--muted)',marginTop:1}}>{fmtIstShort(tx.created_at)}</div>
            </div>
            <div style={{fontWeight:700,fontSize:14,color: tx.amount > 0 ? 'var(--green)' : 'var(--red)',whiteSpace:'nowrap'}}>
              {tx.amount > 0 ? '+' : ''}{tx.amount} 💎
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
