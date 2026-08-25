import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronIcon } from './Icons'
import './Dropdown.css'

// Shared styled replacement for a native <select>, used app-wide — both as a
// compact filter-bar control (variant="filter", the default: pill trigger,
// used e.g. for segment/risk/status filters on Dashboard and Positions) and
// as a full-width form field (variant="form": looks like the app's other
// inputs/selects, used e.g. for account/broker/side pickers in forms).
//
// Pass either a flat `options: [{value, label}]` list, or `groups:
// [{label, options: [...]}]` for a grouped list (mirrors <optgroup>, e.g.
// "Broker Accounts" / "Game Accounts" in account pickers). `value`/onChange
// always refer to a leaf option's value regardless of grouping.
//
// The menu is portaled straight into document.body and positioned with
// `position: fixed` from the trigger's live bounding rect, rather than
// living as a position:absolute child of the trigger. A card buried a few
// levels deep in the page can put the trigger inside a stacking context
// that a plain z-index can't win against every sibling/ancestor of (a
// fixed bottom nav bar, a later card, etc.) — a long options list would
// then render with its lower portion visually covered by that unrelated
// content despite z-index. Portaling to <body> sidesteps that entirely,
// the same approach every serious popover/dropdown library uses.
export default function Dropdown({ value, onChange, options, groups, variant = 'filter', align = 'left', placeholder }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(null)
  const btnRef  = useRef(null)
  const menuRef = useRef(null)

  useLayoutEffect(() => {
    if (!open || !btnRef.current) return
    const rect = btnRef.current.getBoundingClientRect()
    const MENU_MAX = 268 // keep in sync with .dd-menu's max-height + margin
    const spaceBelow = window.innerHeight - rect.bottom
    const spaceAbove = rect.top
    const openUp = spaceBelow < MENU_MAX && spaceAbove > spaceBelow

    const next = { left: rect.left }
    if (variant === 'form') next.width = rect.width
    else next.minWidth = rect.width
    if (openUp) next.bottom = window.innerHeight - rect.top + 6
    else        next.top    = rect.bottom + 6
    if (align === 'right') { next.left = undefined; next.right = window.innerWidth - rect.right }
    setPos(next)
  }, [open, align, variant])

  useEffect(() => {
    if (!open) return
    function onDocPointer(e) {
      if (btnRef.current?.contains(e.target)) return
      if (menuRef.current?.contains(e.target)) return
      setOpen(false)
    }
    function onKey(e) { if (e.key === 'Escape') setOpen(false) }
    function onViewportChange() { setOpen(false) }
    document.addEventListener('mousedown', onDocPointer)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', onViewportChange)

    // Lock background scroll while open — the menu's own list can still be
    // long enough to need its own scrollbar, and this guarantees a scroll
    // gesture always lands on that list rather than the page underneath.
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('mousedown', onDocPointer)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onViewportChange)
      document.body.style.overflow = prevOverflow
    }
  }, [open])

  const flatOptions = groups ? groups.flatMap(g => g.options) : (options || [])
  const current = flatOptions.find(o => o.value === value)
  const label   = current ? current.label : (placeholder || value)

  function renderItem(o) {
    return (
      <div key={o.value} role="option" aria-selected={o.value === value}
           className={`dd-item${o.value === value ? ' selected' : ''}`}
           onClick={() => { onChange(o.value); setOpen(false) }}>
        {o.label}
      </div>
    )
  }

  return (
    <div className={`dd dd-${variant}`}>
      <button ref={btnRef} type="button"
              className={`dd-btn dd-btn-${variant}${open ? ' open' : ''}${!current && placeholder ? ' placeholder' : ''}`}
              onClick={() => setOpen(v => !v)}>
        <span>{label}</span>
        <ChevronIcon size={variant === 'form' ? 13 : 10} open={open} />
      </button>
      {open && pos && createPortal(
        <div ref={menuRef} className={`dd-menu dd-menu-${variant}`}
             style={{ position: 'fixed', ...pos }} role="listbox">
          {groups
            ? groups.map(g => g.options.length > 0 && (
                <div key={g.label}>
                  <div className="dd-group-label">{g.label}</div>
                  {g.options.map(renderItem)}
                </div>
              ))
            : flatOptions.map(renderItem)}
        </div>,
        document.body
      )}
    </div>
  )
}
