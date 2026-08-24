import { useState, useEffect, useRef } from 'react'
import { searchInstruments } from '../../api/trades'

// ─── Instrument search typeahead ─────────────────────────────────────────────

export default function InstrumentSearch({ value, onSelect }) {
  const [query, setQuery]     = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen]       = useState(false)
  const [focused, setFocused] = useState(-1)
  const timerRef = useRef(null)
  const wrapRef  = useRef(null)

  useEffect(() => {
    function onClickOut(e) { if (!wrapRef.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('click', onClickOut)
    return () => document.removeEventListener('click', onClickOut)
  }, [])

  function handleChange(e) {
    const q = e.target.value
    setQuery(q); setFocused(-1)
    clearTimeout(timerRef.current)
    if (q.length < 2) { setOpen(false); setResults([]); return }
    timerRef.current = setTimeout(async () => {
      const res = await searchInstruments(q)
      setResults(res); setOpen(res.length > 0)
    }, 300)
  }

  function handleKey(e) {
    if (!open) return
    if      (e.key === 'ArrowDown') { e.preventDefault(); setFocused(f => Math.min(f + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp')   { e.preventDefault(); setFocused(f => Math.max(f - 1, 0)) }
    else if (e.key === 'Enter' && focused >= 0) { e.preventDefault(); pick(results[focused]) }
    else if (e.key === 'Escape')    setOpen(false)
  }

  function pick(item) { setOpen(false); setQuery(''); setResults([]); onSelect(item) }

  if (value) return (
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'5px 10px',background:'#eff6ff',border:'1px solid #bfdbfe',borderRadius:6,marginBottom:6}}>
      <span style={{fontSize:12,color:'#1d4ed8',fontWeight:500,flex:1}}>{value.label}</span>
      <button style={{background:'none',border:'none',color:'#93c5fd',cursor:'pointer',fontSize:14}} onClick={() => onSelect(null)}>✕</button>
    </div>
  )

  return (
    <div ref={wrapRef} style={{position:'relative',marginBottom:6}}>
      <input placeholder="Search: nifty 25000 ce  /  banknifty fut"
             value={query} onChange={handleChange} onKeyDown={handleKey} autoComplete="off" />
      {open && (
        <div style={{position:'absolute',top:'100%',left:0,right:0,zIndex:200,background:'#fff',
                     border:'1px solid var(--border)',borderTop:'none',borderRadius:'0 0 8px 8px',
                     maxHeight:180,overflowY:'auto',boxShadow:'0 6px 16px rgba(0,0,0,.1)'}}>
          {results.map((r, i) => (
            <div key={i} style={{padding:'8px 12px',cursor:'pointer',fontSize:13,
                                 borderBottom:'1px solid #f1f5f9',
                                 background:i===focused?'#eff6ff':'#fff'}}
                 onMouseEnter={() => setFocused(i)} onClick={() => pick(r)}>{r.label}</div>
          ))}
        </div>
      )}
    </div>
  )
}
