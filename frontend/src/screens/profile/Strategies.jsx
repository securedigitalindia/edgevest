import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useStrategies, useStrategyConfig, useSetStrategyConfig, useStrategyRun } from '../../hooks/useStrategies'
import { useToast } from '../../components/common/Toast'
import PageHeader from '../../components/common/PageHeader'
import SvgChart from './StrategyChart'
import { fmtPnl, fmtPts, fmtIstShort } from '../../utils/format'
import './Profile.css'
import './Strategies.css'

// Admin-only "Strategies" section — research/monitoring view of already-
// backtested strategies. Not a trading signal — see
// docs/prd/admin-strategies-dashboard.md's Non-goals. Two screens on one
// component: /profile/strategies is a plain list (no data pulled), and
// /profile/strategies/:strategyId is the detail (inputs + results) — data
// is only pulled once a strategy has been opened.
export default function Strategies() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'
  const { strategyId } = useParams()

  if (!isAdmin) return <Navigate to="/profile" replace />
  return strategyId ? <StrategyPage strategyId={strategyId} /> : <StrategyList />
}

const WEEKDAY_LABEL = { MON: 'Mon', TUE: 'Tue', WED: 'Wed', THU: 'Thu', FRI: 'Fri' }

// Short chips describing a saved/active input set, per strategy shape.
function inputChips(strategyId, startDate, params = {}) {
  const chips = []
  if (startDate) chips.push(['From', startDate])
  chips.push(['Side', params.side === 'BOTH' || !params.side ? 'PE + CE' : params.side])
  if (strategyId === 'pe_ce_ratio_spread_1x2') {
    chips.push(['Entry day', WEEKDAY_LABEL[params.entry_weekday] || params.entry_weekday || '—'])
    chips.push(['Far-leg offset', params.leg_gap ?? 0])
  } else {
    chips.push(['Leg gap', params.leg_gap ?? '—'])
    chips.push(['Up move', params.trigger?.up_move ?? '—'])
  }
  chips.push(['Strike step', params.strike_multiple ?? '—'])
  chips.push(['Initial gap', params.initial_gap ?? 0])
  return chips
}

function StrategyList() {
  const navigate = useNavigate()
  const { data, isLoading } = useStrategies()
  const strategies = data?.strategies || []

  return (
    <div className="profile-page strat-page">
      <PageHeader title="Strategies" fallback="/profile" />
      <p className="strat-list-caption">
        Backtested strategies for research and monitoring — not trading signals. Open one to set its inputs and see results.
      </p>

      {isLoading && <div className="empty">Loading…</div>}
      {!isLoading && !strategies.length && <div className="empty">No strategies registered yet.</div>}

      <div className="strat-list">
        {strategies.map(s => (
          <button key={s.id} type="button" className="strat-list-card" onClick={() => navigate(`/profile/strategies/${s.id}`)}>
            <div className="strat-list-card-top">
              <span className="strat-list-card-title">{s.label}</span>
              <span className={`strat-status-pill ${s.configured ? 'on' : 'off'}`}>{s.configured ? 'Configured' : 'Not configured'}</span>
            </div>
            <div className="strat-list-card-desc">{s.description}</div>
            <div className="strat-chip-row">
              {(s.summary || []).map(t => <span key={t} className="strat-chip strat-chip-rule">{t}</span>)}
            </div>
            <div className="strat-list-card-foot">
              {s.config
                ? <span>Tracking from {s.config.start_date} · {inputChips(s.id, null, s.config.params).slice(0, 3).map(([k, v]) => `${k} ${v}`).join(' · ')}</span>
                : <span>Set a start date and inputs to begin</span>}
              <span className="strat-list-card-go" aria-hidden="true">›</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function StrategyPage({ strategyId }) {
  const [editing, setEditing] = useState(false)
  const { data: stratResp, isLoading: loadingStrategies } = useStrategies()
  const selected = (stratResp?.strategies || []).find(s => s.id === strategyId) || null

  const { data: configResp, isLoading: loadingConfig } = useStrategyConfig(strategyId)
  // Gate off the confirmed-config row itself (not strategies[].configured) so
  // a freshly-confirmed config flips this view over as soon as its own query
  // refetches — useSetStrategyConfig already invalidates ['strategy-config', id].
  const config     = configResp?.config ?? null
  const configured = !!config

  return (
    <div className="profile-page strat-page">
      <PageHeader title={selected?.label || 'Strategy'} back="/profile/strategies" fallback="/profile/strategies" />

      {loadingStrategies && <div className="empty">Loading…</div>}
      {!loadingStrategies && !selected && <div className="empty">Unknown strategy.</div>}

      {selected && (
        <>
          <p className="strat-list-caption">{selected.description}</p>
          <div className="strat-chip-row" style={{ marginBottom: 16 }}>
            {(selected.summary || []).map(t => <span key={t} className="strat-chip strat-chip-rule">{t}</span>)}
          </div>
        </>
      )}

      {selected && !loadingConfig && (!configured || editing) && (
        <ConfigForm
          strategy={selected}
          existing={config}
          isReconfigure={configured}
          onCancel={configured ? () => setEditing(false) : null}
          onSaved={() => setEditing(false)}
        />
      )}

      {selected && !loadingConfig && configured && !editing && (
        <StrategyDetail strategy={selected} config={config} onEdit={() => setEditing(true)} configVersion={config.confirmed_at} />
      )}

      {selected && loadingConfig && <div className="empty">Loading inputs…</div>}
    </div>
  )
}

// Strategy params vs trigger params are kept as two distinct groups in this
// form, matching the backend's own split (backend/strategies/registry.py,
// 2026-09-09): "leg_gap" is the strategy's own shape (the K/K2 strike
// spread — fixed per entry, doesn't change per trigger); "trigger" is a
// separate, extensible sub-object describing the rule that decides WHEN a
// new 4-leg set gets added (today just one type, "up_move"; a second
// trigger type — e.g. an EMA-cross entry — can be added later without
// reshaping this again). This form is written specifically for that one
// provider's known shape rather than fully generic over any default_params
// — reasonable while pe_ce_ratio_diagonal is the only registered strategy;
// revisit if/when a second one needs its own distinct shape.
function ConfigForm({ strategy, existing, isReconfigure, onCancel, onSaved }) {
  const setConfig = useSetStrategyConfig(strategy.id)
  const toast = useToast()
  const defaults = strategy.default_params || {}
  const seeded = existing?.params || defaults
  const defaultTrigger = defaults.trigger || {}
  const seededTrigger = seeded.trigger || defaultTrigger

  const [startDate, setStartDate] = useState(existing?.start_date || '')
  const [legGap, setLegGap] = useState(seeded.leg_gap ?? defaults.leg_gap ?? '')
  const [strikeMultiple, setStrikeMultiple] = useState(seeded.strike_multiple ?? defaults.strike_multiple ?? '')
  const [initialGap, setInitialGap] = useState(seeded.initial_gap ?? defaults.initial_gap ?? 0)
  const [side, setSide] = useState(seeded.side ?? defaults.side ?? 'BOTH')
  const [upMove, setUpMove] = useState(seededTrigger.up_move ?? defaultTrigger.up_move ?? '')
  // The 1:2 ratio spread has no trigger (one position per weekly window) — it has a weekday instead.
  const isSpread = strategy.id === 'pe_ce_ratio_spread_1x2'
  const [entryWeekday, setEntryWeekday] = useState(seeded.entry_weekday ?? defaults.entry_weekday ?? 'WED')

  function resetToDefaults() {
    setLegGap(defaults.leg_gap ?? '')
    setStrikeMultiple(defaults.strike_multiple ?? '')
    setInitialGap(defaults.initial_gap ?? 0)
    setSide(defaults.side ?? 'BOTH')
    setUpMove(defaultTrigger.up_move ?? '')
    setEntryWeekday(defaults.entry_weekday ?? 'WED')
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (!startDate) { toast('Start date is required', 'err'); return }
    if (legGap === '' || strikeMultiple === '' || (!isSpread && upMove === '')) {
      toast(isSpread ? 'Leg gap and strike rounding are required' : 'Leg gap, strike rounding, and up move are required', 'err')
      return
    }
    const params = {
      leg_gap: Number(legGap),
      strike_multiple: Number(strikeMultiple),
      initial_gap: initialGap === '' ? 0 : Number(initialGap),
      side,
      ...(isSpread
        ? { entry_weekday: entryWeekday }
        // Spread the currently-confirmed trigger (falling back to provider
        // defaults only when nothing's confirmed yet), not defaultTrigger —
        // otherwise any future trigger field beyond up_move would silently
        // revert to the provider's stock default on every reconfigure.
        : { trigger: { ...seededTrigger, up_move: Number(upMove) } }),
    }
    setConfig.mutate({ start_date: startDate, params }, {
      onSuccess: res => {
        if (!res.ok) { toast(res.error || 'Failed to save inputs', 'err'); return }
        toast(isReconfigure ? 'Inputs applied' : `${strategy.label} configured`, 'ok')
        onSaved?.()
      },
    })
  }

  return (
    <form className="strat-config-card" onSubmit={handleSubmit}>
      <div className="strat-config-title">{isReconfigure ? 'Edit inputs' : 'Set inputs to begin'}</div>
      <p className="strat-config-caption">
        {isReconfigure
          ? <>Applying saves these inputs and reloads the results below. Nothing is pulled until you apply.</>
          : <>Pick the date tracking should start from and the inputs below, then apply — results are pulled only after that.</>}
      </p>

      <div className="strat-config-section-label">Strategy</div>
      <div className="strat-config-grid">
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label htmlFor="strat-start-date">Start date</label>
          <input id="strat-start-date" type="date" value={startDate} onChange={e => setStartDate(e.target.value)} required />
        </div>
        {isSpread && (
          <div className="form-row" style={{ marginBottom: 0 }}>
            <label htmlFor="strat-entry-weekday">entry day</label>
            <select id="strat-entry-weekday" value={entryWeekday} onChange={e => setEntryWeekday(e.target.value)}
                    title="One window per week enters at 09:30 IST on this weekday and exits 15:00 IST on the next Monday.">
              {[['MON', 'Monday'], ['TUE', 'Tuesday'], ['WED', 'Wednesday'], ['THU', 'Thursday'], ['FRI', 'Friday']]
                .map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        )}
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label htmlFor="strat-leg-gap">{isSpread ? 'far-leg strike offset (pts, 0 = same strike)' : 'leg gap (K → K2, pts)'}</label>
          <input id="strat-leg-gap" type="number" step="any" value={legGap} onChange={e => setLegGap(e.target.value)} required />
        </div>
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label htmlFor="strat-strike-multiple">strike rounding (pts)</label>
          <input id="strat-strike-multiple" type="number" step="any" value={strikeMultiple}
                 onChange={e => setStrikeMultiple(e.target.value)} required
                 title="K snaps to the next-lower (PE) / next-higher (CE) multiple of this — 100 is NIFTY's real strike spacing" />
        </div>
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label htmlFor="strat-initial-gap">initial gap (pts)</label>
          <input id="strat-initial-gap" type="number" step="any" value={initialGap}
                 onChange={e => setInitialGap(e.target.value)}
                 title="Shifts K before rounding: 0 = nearest OTM (default). Positive = further OTM (PE: K-gap, CE: K+gap). Negative = toward/into ITM (PE: K+|gap|, CE: K-|gap|)." />
        </div>
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label htmlFor="strat-side">side</label>
          <select id="strat-side" value={side} onChange={e => setSide(e.target.value)}
                  title="Which side(s) to actually compute — a side not selected is skipped entirely on the backend, not just hidden.">
            <option value="BOTH">PE + CE</option>
            <option value="PE">PE only</option>
            <option value="CE">CE only</option>
          </select>
        </div>
      </div>
      <p className="strat-config-caption strat-config-caption-tight">
        Initial gap shifts K before the strike-rounding step above — 0 rounds to the nearest strike; a positive value
        pushes K further OTM, negative pulls it toward/into ITM (sign auto-flips for PE vs CE, same convention as leg gap).
      </p>

      {isSpread ? (
        <>
          <div className="strat-config-section-label">Schedule</div>
          <p className="strat-config-caption strat-config-caption-tight">
            Each week buys 1x on the <strong>upcoming expiry</strong> (nearest with more than 2 days to go — a Monday entry skips
            Tuesday&rsquo;s) and sells 2x on the <strong>next expiry after it</strong>. It enters at <strong>09:30 IST</strong> on the
            entry day above and exits at <strong>15:00 IST on the next Monday</strong> (the previous trading day if that Monday is
            a holiday) — fixed by the strategy&rsquo;s definition, not editable. One independent window per week.
          </p>
        </>
      ) : (
        <>
      <div className="strat-config-section-label">Trigger</div>
      <p className="strat-config-caption strat-config-caption-tight">
        Decides when a new 4-leg set gets added. Today: <strong>{seededTrigger.type || 'up_move'}</strong> — fire a fresh
        set every N fut points from the last trigger&rsquo;s own entry (up for PE, down for CE). More trigger types can be
        added here later without changing the strategy above.
      </p>
      <div className="strat-config-grid">
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label htmlFor="strat-up-move">up move (pts)</label>
          <input id="strat-up-move" type="number" step="any" value={upMove} onChange={e => setUpMove(e.target.value)} required />
        </div>
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label>first trigger</label>
          <input type="text" value={seededTrigger.first_trigger_time || '09:30 IST (fixed)'} disabled
                 title="Part of the strategy's locked live-execution rule, not an editable trigger param — changing it would change the strategy's definition." />
        </div>
      </div>
        </>
      )}

      <div className="strat-config-actions">
        <button type="submit" className="btn btn-primary" disabled={setConfig.isPending}>
          {setConfig.isPending ? 'Applying…' : 'Apply & run'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={resetToDefaults}>Reset to defaults</button>
        {onCancel && <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>}
      </div>

      {existing?.confirmed_by && (
        <div className="strat-config-meta">Last confirmed by {existing.confirmed_by}{existing.confirmed_at ? ` · ${fmtIstShort(existing.confirmed_at)}` : ''}</div>
      )}
    </form>
  )
}

function StrategyDetail({ strategy, config, onEdit, configVersion }) {
  const { data, isLoading, isFetching } = useStrategyRun(strategy.id, { enabled: true, configVersion })
  const windows = data?.windows || []
  const [selectedWindow, setSelectedWindow] = useState(null)
  // Which side(s) actually got computed is a CONFIG decision (params.side,
  // 2026-09-09) — the backend skips a non-selected side's compute entirely
  // rather than this screen filtering it out after the fact. Default to
  // BOTH only until the real value loads, so the layout doesn't flash.
  const side = data?.side || 'BOTH'

  // Default to the newest (most recently opened) window, without stomping on
  // a user's own tab pick across the ~1-minute background refetch — only
  // re-picks when the currently-selected window no longer exists.
  useEffect(() => {
    if (!windows.length) return
    if (!selectedWindow || !windows.some(w => w.entry_date === selectedWindow)) {
      setSelectedWindow(windows[windows.length - 1].entry_date)
    }
  }, [windows, selectedWindow])

  const win = windows.find(w => w.entry_date === selectedWindow) || null

  return (
    <>
      <div className="strat-inputs-summary">
        <div className="strat-inputs-summary-head">
          <span className="strat-inputs-summary-title">Inputs</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onEdit}>Edit inputs</button>
        </div>
        <div className="strat-chip-row">
          {inputChips(strategy.id, config.start_date, config.params).map(([k, v]) => (
            <span key={k} className="strat-chip"><span className="strat-chip-k">{k}</span> {v}</span>
          ))}
          {data?.fut_trading_symbol && <span className="strat-chip"><span className="strat-chip-k">Price</span> {data.fut_trading_symbol}</span>}
        </div>
      </div>

      {data?.data_as_of && (
        <div className="strat-freshness-banner">Data as of {data.data_as_of}{isFetching && !isLoading ? ' · refreshing…' : ''}</div>
      )}

      {isLoading && <div className="empty">Pulling data for this configuration… (recomputes any new/open window — settled windows are cached and load instantly next time)</div>}
      {!isLoading && data && data.ok === false && <div className="empty">{data.error || 'No usable result for this strategy yet.'}</div>}
      {!isLoading && data && data.ok !== false && !windows.length && <div className="empty">No windows yet for the configured start date.</div>}

      {!isLoading && windows.length > 0 && (
        <div className="strat-window-tabs" role="tablist" aria-label="Window">
          {windows.map(w => (
            <button key={w.entry_date} type="button" role="tab" aria-selected={w.entry_date === selectedWindow}
              className={`strat-window-tab ${w.entry_date === selectedWindow ? 'strat-window-tab-active' : ''}`}
              onClick={() => setSelectedWindow(w.entry_date)}>
              <span>{w.entry_date}{!w.is_bounded && <span className="strat-window-tab-open-chip">OPEN</span>}</span>
              <span className="strat-window-tab-sub">
                {[side !== 'CE' && `PE ${fmtPts(w.pe_realized_pnl_pts)}`, side !== 'PE' && `CE ${fmtPts(w.ce_realized_pnl_pts)}`].filter(Boolean).join(' · ')}
              </span>
            </button>
          ))}
        </div>
      )}

      {win && <WindowPanel win={win} side={side} strategyId={strategy.id} />}
    </>
  )
}

function WindowPanel({ win, side, strategyId }) {
  const isSpread = strategyId === 'pe_ce_ratio_spread_1x2'
  const combinedPts = (win.pe_realized_pnl_pts || 0) + (win.ce_realized_pnl_pts || 0)
  const sets = (win.sets || []).filter(s => side === 'BOTH' || s.side === side)
  const peSets = sets.filter(s => s.side === 'PE')
  const ceSets = sets.filter(s => s.side === 'CE')
  const showPe = side === 'PE' || side === 'BOTH'
  const showCe = side === 'CE' || side === 'BOTH'

  return (
    <div>
      <div className="strat-tiles">
        <div className="strat-tile">
          <div className="strat-tile-label">{isSpread ? 'Positions entered' : 'Sets triggered'}</div>
          <div className="strat-tile-value">{sets.length}</div>
          <div className="strat-tile-sub">{peSets.length} PE · {ceSets.length} CE</div>
        </div>
        {showPe && <div className="strat-tile">
          <div className="strat-tile-label"><span className="strat-tile-dot" style={{ background: 'var(--pe-color)' }} />PE{win.is_bounded ? ' realized' : ''}{!win.pe_ok && ' — unavailable'}</div>
          <div className={`strat-tile-value ${win.pe_realized_pnl_pts >= 0 ? 'pos' : 'neg'}`}>{fmtPts(win.pe_realized_pnl_pts)} pts</div>
          <div className="strat-tile-sub">{fmtPnl(win.pe_realized_pnl_rs)}</div>
          {win.is_bounded && <div className="strat-tile-sub">if held: {fmtPts(win.pe_ref_pnl_pts)} pts</div>}
        </div>}
        {showCe && <div className="strat-tile">
          <div className="strat-tile-label"><span className="strat-tile-dot" style={{ background: 'var(--ce-color)' }} />CE{win.is_bounded ? ' realized' : ''}{!win.ce_ok && ' — unavailable'}</div>
          <div className={`strat-tile-value ${win.ce_realized_pnl_pts >= 0 ? 'pos' : 'neg'}`}>{fmtPts(win.ce_realized_pnl_pts)} pts</div>
          <div className="strat-tile-sub">{fmtPnl(win.ce_realized_pnl_rs)}</div>
          {win.is_bounded && <div className="strat-tile-sub">if held: {fmtPts(win.ce_ref_pnl_pts)} pts</div>}
        </div>}
        {side === 'BOTH' && (
          <div className="strat-tile strat-tile-secondary" title="Reference only — PE and CE are two independent strategies; this is just their sum.">
            <div className="strat-tile-label"><span className="strat-tile-dot" style={{ background: 'var(--combined-color)' }} />Combined (PE+CE)</div>
            <div className={`strat-tile-value ${combinedPts >= 0 ? 'pos' : 'neg'}`}>{fmtPts(combinedPts)} pts</div>
            <div className="strat-tile-sub">reference only — never actually summed</div>
          </div>
        )}
      </div>

      <div className="strat-section-title">{isSpread ? 'Positions' : 'Triggered Sets'}</div>
      <SetCards sets={sets} isBounded={win.is_bounded} isSpread={isSpread}
                windowLatestTs={win.combined?.length ? win.combined[win.combined.length - 1].ts : null} />

      <FuturesPanel win={win} sets={sets} />
      <PnlPanel win={win} side={side} />

      <div className="strat-section-title">Daily close — realized</div>
      <DailyTable rows={win.daily_realized || []} side={side} />

      {win.is_bounded && (win.daily_reference || []).length > 0 && (
        <>
          <div className="strat-section-title">Daily close — if held to actual settlement</div>
          <DailyTable rows={win.daily_reference} side={side} muted />
        </>
      )}
    </div>
  )
}

const pad12 = (lo, hi) => { const p = (hi - lo) * 0.12 || 10; return [lo - p, hi + p] }

// Two separate charts, matching the artifact exactly — a futures reference
// price chart and a position P&L chart are two different questions ("where
// did the market go" vs "what did the position do about it") and reading
// them off two independent y-axes is clearer than one dual-axis chart.
function FuturesPanel({ win, sets }) {
  const combined = win.combined || []
  if (!combined.length) return null
  const points = combined.map((p, idx) => ({ ...p, idx }))
  const futVals = points.map(p => p.fut)
  const markers = sets.filter(s => s.entry_value != null).map(s => ({
    ts: s.trigger_ts, key: 'fut', label: s.side, color: s.side === 'PE' ? 'var(--pe-color)' : 'var(--ce-color)',
  }))
  return (
    <div className="strat-panel">
      <div className="strat-panel-head">
        <div className="strat-panel-title">NIFTY futures — reference price</div>
        <div className="strat-panel-sub">{combined.length} ticks · dots mark each set&rsquo;s trigger{win.is_bounded && ' · red line marks exit'}</div>
      </div>
      <SvgChart points={points} height={200} yDomain={pad12(Math.min(...futVals), Math.max(...futVals))}
                series={[{ key: 'fut', color: 'var(--muted)', label: 'NIFTY FUT' }]}
                markers={markers} exitTs={win.is_bounded ? win.exit_ts : null} />
    </div>
  )
}

function PnlPanel({ win, side }) {
  const combined = win.combined || []
  if (!combined.length) return null
  const points = combined.map((p, idx) => ({ ...p, idx }))
  const allSeries = [
    { key: 'pe_pnl_pts', phase: true, color: 'var(--pe-color)', label: 'PE P&L' },
    { key: 'ce_pnl_pts', phase: true, color: 'var(--ce-color)', label: 'CE P&L' },
    { key: 'total_pnl_pts', phase: true, color: 'var(--combined-color)', label: 'Combined (PE+CE)', dp: 2 },
  ]
  const series = side === 'BOTH' ? allSeries : allSeries.filter(s => s.key === `${side.toLowerCase()}_pnl_pts`)
  const vals = points.flatMap(p => series.map(s => p[s.key])).concat(0)
  const hasPostExit = combined.some(p => p.post_exit)
  return (
    <div className="strat-panel">
      <div className="strat-panel-head">
        <div className="strat-panel-title">Position P&amp;L — {side === 'BOTH' ? 'PE, CE, and Combined' : side}</div>
        <div className="strat-panel-sub">Solid = realized so far, dashed/muted = if held past exit (reference only){!win.is_bounded && ' · window still open'}</div>
      </div>
      <SvgChart points={points} height={220} zeroLine yDomain={pad12(Math.min(...vals), Math.max(...vals))}
                series={series} exitTs={win.is_bounded ? win.exit_ts : null}
                legend={side === 'BOTH' ? [...series.map(s => ({ label: s.label, color: s.color })), ...(hasPostExit ? [{ label: 'if held (reference)', dashed: true }] : [])] : undefined} />
    </div>
  )
}

function SetCards({ sets, isBounded, isSpread, windowLatestTs }) {
  const priced = sets.filter(s => s.entry_value != null)
  if (!priced.length) return <div className="empty" style={{ marginBottom: 16 }}>{isSpread ? 'No position could be priced in this window.' : 'No triggered sets in this window.'}</div>
  return (
    <div className="strat-set-grid">
      {priced.map((s, i) => {
        const color = s.side === 'PE' ? 'var(--pe-color)' : 'var(--ce-color)'
        // A set within a still-OPEN window can itself already be closed — once
        // its own near-leg expiry settles, its data stops updating and its
        // contribution freezes (see run_window()'s own freeze behavior) even
        // though a LATER-triggered set in the same window is still live. Detect
        // that by comparing this set's own last_ts against the window's overall
        // latest tick: earlier means this set's own position is done, not "current."
        const setClosed = isBounded || (windowLatestTs != null && s.last_ts != null && s.last_ts < windowLatestTs)
        return (
          <div key={`${s.trigger_ts}-${i}`} className={`strat-set-card ${s.never_filled_before_rollover ? 'dropped' : ''}`}
               style={{ '--set-color': color }}>
            <div className="strat-set-label">
              <span className="strat-side-pill" style={{ background: color }}>{s.side}</span>
              {isSpread ? 'entered' : 'triggered'} {fmtIstShort(s.trigger_ts)}
            </div>
            <div className="strat-set-strikes">{s.k_strike?.toFixed(0)} / {s.k2_strike?.toFixed(0)}</div>
            <div className="strat-set-meta">
              <span>fut @ trigger: {s.trigger_fut?.toFixed(1)}</span>
              <span>expiries {[s.expiry1, s.expiry2, s.expiry3].filter(Boolean).map(d => d.slice(5)).join(' / ')}</span>
            </div>
            <div className="strat-set-entry"><span className="v">{s.entry_value.toFixed(2)}</span><span className="u">pts entry debit</span></div>
            {/* Exit debit for anything actually closed — the whole window settled,
                OR (2026-09-09) this one older set's own near-leg already expired
                even though the window itself is still open because a newer set
                is still live. Always exit_value (capped to this set's own real
                exit_ts) — for an individually-closed set in an open window that's
                identical to current_value anyway (no window-level exit boundary
                to cap against), but for a bounded window current_value could be
                the "if held past exit" figure instead, which must not show here.
                "current debit" (still genuinely moving) only for a set that isn't
                closed at all. */}
            {setClosed && s.exit_value != null && (
              <SetValueRow label="pts exit debit" value={s.exit_value} entryValue={s.entry_value} />
            )}
            {!setClosed && s.current_value != null && (
              <SetValueRow label="pts current debit" value={s.current_value} entryValue={s.entry_value} />
            )}
            {s.strike_overrides && (
              <div className="strat-set-note">strike fallback used: {Object.entries(s.strike_overrides).map(([leg, st]) => `${leg}→${st}`).join(', ')}</div>
            )}
            {s.never_filled_before_rollover && (
              <div className="strat-set-note">Dropped — never filled before this window&rsquo;s rollover</div>
            )}
            <LegBreakdown s={s} setClosed={setClosed} isSpread={isSpread} />
          </div>
        )
      })}
    </div>
  )
}

// l1=BUY 1x K@expiry1, l2=SELL 2x K2@expiry2, l3=SELL 1x K@expiry2,
// l4=BUY 2x K2@expiry3 — fixed strategy shape, same mapping both sides
// (only which value is "K" vs "K2" differs, already reflected in
// k_strike/k2_strike). See docs/prd/pe-ratio-diagonal-strategy.md.
const LEG_META = {
  l1: { action: 'BUY 1x', strikeKey: 'k_strike', expiryKey: 'expiry1' },
  l2: { action: 'SELL 2x', strikeKey: 'k2_strike', expiryKey: 'expiry2' },
  l3: { action: 'SELL 1x', strikeKey: 'k_strike', expiryKey: 'expiry2' },
  l4: { action: 'BUY 2x', strikeKey: 'k2_strike', expiryKey: 'expiry3' },
}

// 1:2 calendar ratio: l1=BUY 1x K on the upcoming expiry, l2=SELL 2x K2 on the next expiry after it.
const SPREAD_LEG_META = {
  l1: { action: 'BUY 1x', strikeKey: 'k_strike', expiryKey: 'expiry1' },
  l2: { action: 'SELL 2x', strikeKey: 'k2_strike', expiryKey: 'expiry2' },
}

function LegBreakdown({ s, setClosed, isSpread }) {
  if (!s.entry_legs) return null
  const laterLegs = setClosed ? s.exit_legs : s.current_legs
  const laterLabel = setClosed ? 'exit' : 'now'
  return (
    <div className="strat-leg-table-wrap">
      <table className="strat-leg-table">
        <thead>
          <tr><th>Leg</th><th>Strike</th><th>Expiry</th><th>Entry</th><th>{laterLabel}</th></tr>
        </thead>
        <tbody>
          {Object.entries(isSpread ? SPREAD_LEG_META : LEG_META).map(([leg, m]) => (
            <tr key={leg}>
              <td>{m.action}</td>
              <td>{s[m.strikeKey]?.toFixed(0)}</td>
              <td>{s[m.expiryKey]?.slice(5)}</td>
              <td>{s.entry_legs[leg]?.toFixed(2)}</td>
              <td>{laterLegs?.[leg] != null ? laterLegs[leg].toFixed(2) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SetValueRow({ label, value, entryValue }) {
  const delta = value - entryValue
  return (
    <div className="strat-set-entry">
      <span className="v">{value.toFixed(2)}</span>
      <span className="u">{label}</span>
      <span className={`strat-set-delta ${delta >= 0 ? 'pos' : 'neg'}`}>{delta >= 0 ? '+' : ''}{delta.toFixed(2)}</span>
    </div>
  )
}

function DailyTable({ rows, side, muted }) {
  if (!rows.length) return <div className="empty" style={{ marginBottom: 16 }}>No data.</div>
  const showPe = side === 'PE' || side === 'BOTH'
  const showCe = side === 'CE' || side === 'BOTH'
  return (
    <div className={`strat-daily-block ${muted ? 'strat-daily-muted' : ''}`}>
      <div className="strat-table-wrap">
        <table className="strat-table">
          <thead>
            <tr>
              <th>Day</th>
              {showPe && <th>PE pts</th>}
              {showCe && <th>CE pts</th>}
              {side === 'BOTH' && <th className="combined-col">Combined pts</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.day}>
                <td>{r.day}</td>
                {showPe && <td style={{ color: r.pe_pnl_pts >= 0 ? 'var(--good)' : 'var(--bad)' }}>{fmtPts(r.pe_pnl_pts)}</td>}
                {showCe && <td style={{ color: r.ce_pnl_pts >= 0 ? 'var(--good)' : 'var(--bad)' }}>{fmtPts(r.ce_pnl_pts)}</td>}
                {side === 'BOTH' && <td className="combined-col">{fmtPts(r.total_pnl_pts)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
