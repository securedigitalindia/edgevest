import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import useAuthStore from '../../store/authStore'
import { useStrategies, useStrategyConfig, useSetStrategyConfig, useStrategyRun } from '../../hooks/useStrategies'
import { useToast } from '../../components/common/Toast'
import PageHeader from '../../components/common/PageHeader'
import SvgChart from './StrategyChart'
import { fmtPnl, fmtPts, fmtIstShort } from '../../utils/format'
import './Profile.css'
import './Strategies.css'

// Admin-only "Strategies" dashboard — research/monitoring view of already-
// backtested strategies (starts with PE+CE Ratio Diagonal). Not a trading
// signal — see docs/prd/admin-strategies-dashboard.md's Non-goals.
export default function Strategies() {
  const user    = useAuthStore(s => s.user)
  const isAdmin = user?.role === 'super_admin' || user?.role === 'admin'

  const { data: stratResp, isLoading: loadingStrategies } = useStrategies()
  const strategies = stratResp?.strategies || []

  const [selectedId, setSelectedId] = useState(null)
  const [reconfiguring, setReconfiguring] = useState(false)

  // Default to the first registered strategy once the list loads (today
  // there's exactly one — PE+CE Ratio Diagonal).
  useEffect(() => {
    if (!selectedId && strategies.length) setSelectedId(strategies[0].id)
  }, [strategies, selectedId])

  const selected = strategies.find(s => s.id === selectedId) || null

  const { data: configResp, isLoading: loadingConfig } = useStrategyConfig(selectedId)
  // Gate off the confirmed-config row itself (not strategies[].configured) so
  // a freshly-confirmed config flips this view over as soon as its own query
  // refetches — useSetStrategyConfig already invalidates ['strategy-config', id].
  const config    = configResp?.config ?? null
  const configured = !!config

  if (!isAdmin) return <Navigate to="/profile" replace />

  return (
    <div className="profile-page strat-page">
      <PageHeader title="Strategies" fallback="/profile" />

      {loadingStrategies && <div className="empty">Loading…</div>}
      {!loadingStrategies && !strategies.length && <div className="empty">No strategies registered yet.</div>}

      {strategies.length > 0 && (
        <div className="strat-picker" role="tablist" aria-label="Strategy">
          {strategies.map(s => (
            <button key={s.id} type="button" role="tab" aria-selected={s.id === selectedId}
              className={`strat-picker-btn ${s.id === selectedId ? 'strat-picker-btn-active' : ''}`}
              onClick={() => { setSelectedId(s.id); setReconfiguring(false) }}>
              {s.label}
              {!s.configured && <span className="strat-configured-dot" title="Not configured yet" />}
            </button>
          ))}
        </div>
      )}

      {selected && !loadingConfig && (!configured || reconfiguring) && (
        <ConfigForm
          strategy={selected}
          existing={config}
          isReconfigure={configured}
          onCancel={configured ? () => setReconfiguring(false) : null}
          onSaved={() => setReconfiguring(false)}
        />
      )}

      {selected && !loadingConfig && configured && !reconfiguring && (
        <StrategyDetail strategy={selected} onReconfigure={() => setReconfiguring(true)} configVersion={config.confirmed_at} />
      )}

      {selected && loadingConfig && <div className="empty">Loading configuration…</div>}
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

  function handleSubmit(e) {
    e.preventDefault()
    if (!startDate) { toast('Start date is required', 'err'); return }
    if (legGap === '' || strikeMultiple === '' || upMove === '') {
      toast('Leg gap, strike rounding, and up move are required', 'err')
      return
    }
    const params = {
      leg_gap: Number(legGap),
      strike_multiple: Number(strikeMultiple),
      initial_gap: initialGap === '' ? 0 : Number(initialGap),
      side,
      // Spread the currently-confirmed trigger (falling back to provider
      // defaults only when nothing's confirmed yet), not defaultTrigger —
      // otherwise any future trigger field beyond up_move would silently
      // revert to the provider's stock default on every reconfigure.
      trigger: { ...seededTrigger, up_move: Number(upMove) },
    }
    setConfig.mutate({ start_date: startDate, params }, {
      onSuccess: res => {
        if (!res.ok) { toast(res.error || 'Failed to save configuration', 'err'); return }
        toast(isReconfigure ? 'Configuration updated' : `${strategy.label} configured`, 'ok')
        onSaved?.()
      },
    })
  }

  return (
    <form className="strat-config-card" onSubmit={handleSubmit}>
      <div className="strat-config-title">{isReconfigure ? `Reconfigure ${strategy.label}` : `Confirm ${strategy.label} config`}</div>
      <p className="strat-config-caption">
        {isReconfigure
          ? <>Re-saving overwrites the current start date/params. This does <strong>not</strong> retroactively invalidate
              already-cached backend windows from the previous configuration — a changed start date just produces new
              window boundaries; old cached windows are simply never read again.</>
          : <>Pick the date this strategy&rsquo;s tracking should start from, and confirm its parameters below.</>}
      </p>

      <div className="strat-config-section-label">Strategy</div>
      <div className="strat-config-grid">
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label htmlFor="strat-start-date">Start date</label>
          <input id="strat-start-date" type="date" value={startDate} onChange={e => setStartDate(e.target.value)} required />
        </div>
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label htmlFor="strat-leg-gap">leg gap (K → K2, pts)</label>
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

      <div className="strat-config-actions">
        <button type="submit" className="btn btn-primary" disabled={setConfig.isPending}>
          {setConfig.isPending ? 'Saving…' : 'Confirm'}
        </button>
        {onCancel && <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>}
      </div>

      {existing?.confirmed_by && (
        <div className="strat-config-meta">Last confirmed by {existing.confirmed_by}{existing.confirmed_at ? ` · ${fmtIstShort(existing.confirmed_at)}` : ''}</div>
      )}
    </form>
  )
}

function StrategyDetail({ strategy, onReconfigure, configVersion }) {
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
      <div className="strat-detail-header">
        <div className="strat-scope-caption">
          {strategy.label} · side {side === 'BOTH' ? 'PE + CE' : side} · leg_gap {data?.leg_gap ?? '—'} ·
          strike {data?.strike_multiple ?? '—'} · initial gap {data?.initial_gap ?? 0} ·
          up_move {data?.up_move ?? '—'} · {data?.fut_trading_symbol || ''}
        </div>
        <button type="button" className="btn btn-ghost btn-sm strat-reconfigure-btn" onClick={onReconfigure}>Reconfigure to change side/params</button>
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
              <span className="strat-window-tab-sub">PE {fmtPts(w.pe_realized_pnl_pts)} · CE {fmtPts(w.ce_realized_pnl_pts)}</span>
            </button>
          ))}
        </div>
      )}

      {win && <WindowPanel win={win} side={side} />}
    </>
  )
}

function WindowPanel({ win, side }) {
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
          <div className="strat-tile-label">Sets triggered</div>
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

      <div className="strat-section-title">Triggered Sets</div>
      <SetCards sets={sets} isBounded={win.is_bounded}
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

function SetCards({ sets, isBounded, windowLatestTs }) {
  const priced = sets.filter(s => s.entry_value != null)
  if (!priced.length) return <div className="empty" style={{ marginBottom: 16 }}>No triggered sets in this window.</div>
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
              triggered {fmtIstShort(s.trigger_ts)}
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
            <LegBreakdown s={s} setClosed={setClosed} />
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

function LegBreakdown({ s, setClosed }) {
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
          {Object.entries(LEG_META).map(([leg, m]) => (
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
