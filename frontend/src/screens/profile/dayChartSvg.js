// Pure SVG builder for the Day view's stacked chart — a direct port of the shareable artifact's panelChart()
// (backend/analysis/strategy_viewer/template.html) so the dashboard and the artifact draw identically.
// Returns { svg, W, H, X } where svg is the inner markup (self-generated: numbers, dates and strategy labels only).
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
const f1 = v => v == null ? '–' : (Math.round(v * 10) / 10).toLocaleString('en-IN')

export function buildPanelSvg(labels, panels, o = {}) {
  const W = 920, Lp = 58, Rp = 16, n = labels.length, GAPH = 30
  const X = i => Lp + (n < 2 ? 0 : i / (n - 1) * (W - Lp - Rp))
  let y0 = 8, svg = ''
  panels.forEach(p => {
    const vals = []
    p.series.forEach(s => s.y.forEach(v => { if (v != null && isFinite(v)) vals.push(v) }))
    ;(p.hlines || []).forEach(l => vals.push(l.y)); if (p.zero) vals.push(0)
    if (!vals.length) vals.push(0, 1)
    let lo = Math.min(...vals), hi = Math.max(...vals); if (hi === lo) { hi += 1; lo -= 1 }
    const pad = (hi - lo) * .1; lo -= pad; hi += pad
    const t0 = y0   // captured: the closure must not read y0 later (it is advanced below)
    p.top = t0; p.Y = v => t0 + p.h - (v - lo) / (hi - lo) * p.h; p.lo = lo; p.hi = hi
    y0 += p.h + GAPH
  })
  const H = y0 - GAPH + 26
  const C = o.colors
  if (o.shade) svg += `<rect x="${X(o.shade[0])}" y="4" width="${Math.max(0, X(o.shade[1]) - X(o.shade[0]))}" height="${H - 30}" fill="${C.shade}"/>`
  panels.forEach(p => {
    for (let k = 0; k <= 4; k++) {
      const v = p.lo + (p.hi - p.lo) * k / 4, y = p.Y(v)
      svg += `<line x1="${Lp}" x2="${W - Rp}" y1="${y}" y2="${y}" stroke="${C.grid}"/><text x="${Lp - 6}" y="${y + 4}" text-anchor="end" font-size="11" fill="${C.mut}">${(p.fmt || f1)(v)}</text>`
    }
    if (p.zero) svg += `<line x1="${Lp}" x2="${W - Rp}" y1="${p.Y(0)}" y2="${p.Y(0)}" stroke="${C.mut}" stroke-dasharray="3 3"/>`
    ;(p.hlines || []).forEach(l => { svg += `<line x1="${Lp}" x2="${W - Rp}" y1="${p.Y(l.y)}" y2="${p.Y(l.y)}" stroke="${l.color || C.mut}" stroke-dasharray="${l.dash || '5 4'}"/><text x="${W - Rp}" y="${p.Y(l.y) - 3}" text-anchor="end" font-size="11" fill="${l.color || C.mut}">${esc(l.label)}</text>` })
    p.series.forEach(s => {
      const seg = (a, b, dash, op) => {
        let d = '', pen = false
        for (let i = a; i <= b; i++) { const v = s.y[i]; if (v == null) { pen = false; continue } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + p.Y(v).toFixed(1); pen = true }
        return d ? `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.w || 2}" stroke-linejoin="round" ${dash ? 'stroke-dasharray="4 3"' : ''} opacity="${op}"/>` : ''
      }
      if (s.split != null) svg += seg(0, s.split, true, .55) + seg(s.split, n - 1, false, 1); else svg += seg(0, n - 1, false, s.op || 1)
    })
    ;(p.marks || []).forEach(m => {
      if (m.v == null) return
      const x = X(m.i), y = p.Y(m.v), up = m.pos !== 'below'
      svg += `<circle cx="${x}" cy="${y}" r="4.5" fill="${m.color}" stroke="${C.card}" stroke-width="2"/><text x="${Math.min(Math.max(x, Lp + 30), W - 40)}" y="${y + (up ? -9 : 17)}" text-anchor="middle" font-size="11" font-weight="600" fill="${m.color}">${esc(m.label)}</text>`
    })
    svg += `<text x="${Lp}" y="${p.top - 1}" font-size="11" fill="${C.mut}">${esc(p.title || '')}</text>`
  })
  ;(o.vlines || []).forEach(v => {
    svg += `<line x1="${X(v.i)}" x2="${X(v.i)}" y1="4" y2="${H - 30}" stroke="${v.color}" stroke-dasharray="4 3" stroke-width="1.5"/>`
    if (o.vlabels !== false || v.strong) svg += `<text x="${X(v.i) + 4}" y="14" font-size="11" font-weight="600" fill="${v.color}">${esc(v.label)}</text>`
  })
  const step = Math.max(1, Math.ceil(n / (o.xt || 8)))
  for (let i = 0; i < n; i += step) svg += `<text x="${X(i)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="${C.mut}">${esc(labels[i])}</text>`
  return { svg, W, H, X, Lp, Rp }
}
