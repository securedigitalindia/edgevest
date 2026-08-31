import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useRecs } from '../hooks/useTrades'
import { useMonthlyReport } from '../hooks/useReports'
import { listGames, getMyReferrals } from '../api/games'
import { shortMonthLabel, currentIstMonth, roi } from './profile/reportUtils'
import MonthSummaryCard from './profile/MonthSummaryCard'
import { ChartIcon, PeopleIcon, GameIcon, BookIcon } from '../components/common/Icons'
import { ARTICLES } from '../content/education'
import './Dashboard.css'

// ─── Featured tile — one compact nav tile per feature (Trades, Reports,
// Refer & Earn, Games), each with one standout live stat as a ribbon.
// Mirrors the reference layout signed off in the design mockup: ribbon +
// icon + title + subtitle, not a big numeric "value" like the old stat
// cards — that fuller detail lives on the destination screen. ─────────────

function FeaturedTile({ color, icon, ribbon, ribbonColor, title, subtitle, onClick, wide }) {
  return (
    <div className={`ov-tile ov-tile-${color}${wide ? ' ov-tile-wide' : ''}`} onClick={onClick}>
      {ribbon && <span className={`ov-ribbon ov-ribbon-${ribbonColor}`}>{ribbon}</span>}
      <div className={`ov-tile-icon ov-tile-icon-${color}`}>{icon}</div>
      <div className="ov-tile-title">{title}</div>
      <div className="ov-tile-sub">{subtitle}</div>
    </div>
  )
}

function FeaturedGrid() {
  const navigate = useNavigate()

  const { data: recs = [] } = useRecs()
  const activeCount = recs.filter(r => r.status === 'open').length

  const { data: refData } = useQuery({ queryKey: ['my-referrals'], queryFn: getMyReferrals })
  const rewardGems = refData?.reward_gems

  const { data: monthData } = useMonthlyReport()
  const bookedCount = (monthData?.pnl_events || []).length
  const bookedRoi   = bookedCount > 0 ? roi(monthData.realized_pnl_total, monthData.avg_margin_used) : null
  const month       = currentIstMonth()
  const monthShort  = shortMonthLabel(month) // "Aug" — goes in the ribbon so the month is visible even with no ROI yet

  const { data: games = [] } = useQuery({ queryKey: ['games'], queryFn: listGames, refetchInterval: 60000 })
  const liveGamesCount = games.filter(g => g.status === 'active').length

  return (
    <>
      <div className="ov-section-label">Featured</div>
      <div className="ov-tile-grid">
        <FeaturedTile
          color="blue" ribbonColor="green" icon={<ChartIcon size={22}/>}
          ribbon={`${activeCount} open now`}
          title="Trades" subtitle="Recommended positions"
          onClick={() => navigate('/trades')} />
        <FeaturedTile
          color="indigo" ribbonColor="blue" icon={<ChartIcon size={22}/>}
          ribbon={bookedRoi ? `${monthShort}: ${bookedRoi.text} ROI` : monthShort}
          title="Reports" subtitle="Monthly performance"
          onClick={() => navigate('/profile/reports')} />
        <FeaturedTile
          color="amber" ribbonColor="amber" icon={<PeopleIcon size={22}/>}
          ribbon={rewardGems != null ? `${rewardGems} gems` : null}
          title="Refer & Earn" subtitle="Invite a friend, you both earn gems"
          onClick={() => navigate('/profile/referrals')} />
        <FeaturedTile
          color="green" ribbonColor={liveGamesCount > 0 ? 'green' : 'muted'} icon={<GameIcon size={22}/>}
          ribbon={liveGamesCount > 0 ? `${liveGamesCount} live` : 'Play & earn'}
          title="Games" subtitle="Predictions & challenges"
          onClick={() => navigate('/games')} />
        <FeaturedTile
          wide
          color="teal" ribbonColor="teal" icon={<BookIcon size={22}/>}
          ribbon={`${ARTICLES.length} guides`}
          title="Learn Trading & Investing" subtitle="How EdgeVest's strategies work, and the F&O basics behind them"
          onClick={() => navigate('/profile/learn')} />
      </div>
    </>
  )
}

// ─── Footer — closing tagline + brand mark, per the design mockup. ────────

function DashboardFooter() {
  return (
    <div className="ov-footer">
      <div className="ov-footer-tag">Be Financially Free with <span className="ov-footer-brand">EdgeVest</span></div>
      <div className="ov-footer-made">
        <span className="ov-flag"><span/><span/><span/></span>
        Made in India
      </div>
    </div>
  )
}

// ─── Screen ───────────────────────────────────────────────────────────────

export default function Dashboard() {
  return (
    <div className="ov-layout">
      <FeaturedGrid />
      <MonthSummaryCard />
      <DashboardFooter />
    </div>
  )
}
