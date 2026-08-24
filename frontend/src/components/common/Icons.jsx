// Small inline icons (stroke-based, 24×24 viewBox) — shared wherever the app
// needs the account-row / trend-indicator visual language introduced by the
// Positions page redesign (design canvas:
// https://claude.ai/code/artifact/c7bf2132-d2e0-4f58-98a6-9305fbddf7cd).

export function BankIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 21h18"/><path d="M5 21V9l7-5 7 5v12"/><path d="M9 21v-6h6v6"/>
    </svg>
  )
}

export function GameIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="10" rx="4"/><path d="M7 10v4M5 12h4"/><circle cx="16" cy="10.5" r="1"/><circle cx="18.5" cy="13" r="1"/>
    </svg>
  )
}

export function ChevronIcon({ size = 14, open }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
         style={{transform: open ? 'rotate(180deg)' : 'none', transition:'transform .15s'}}>
      <path d="M6 9l6 6 6-6"/>
    </svg>
  )
}

export function PlusIcon({ size = 13 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 5v14M5 12h14"/>
    </svg>
  )
}

export function TrendIcon({ size = 14, up }) {
  // Base path's arrowhead sits at the top-right (17,7) — an up-right
  // ("growth") arrow by default. Flip it to point down-right for the
  // negative case rather than the positive one.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round"
         style={{transform: up ? 'none' : 'scaleY(-1)'}}>
      <path d="M17 7L7 17M17 7H9M17 7V15"/>
    </svg>
  )
}
