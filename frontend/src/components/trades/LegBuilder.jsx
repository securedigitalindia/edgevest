import InstrumentSearch from './InstrumentSearch'
import { newLeg } from './legHelpers'
import { CloseIcon, PlusIcon } from '../common/Icons'

// ─── Leg builder ─────────────────────────────────────────────────────────────

export default function LegBuilder({ legs, onChange }) {
  function add()            { onChange([...legs, newLeg()]) }
  function remove(id)       { onChange(legs.filter(l => l.id !== id)) }
  function update(id, f, v) { onChange(legs.map(l => l.id === id ? { ...l, [f]: v } : l)) }

  return (
    <div>
      <div style={{display:'flex',flexDirection:'column',gap:10,marginBottom:10}}>
        {legs.map((leg, i) => (
          <div key={leg.id} style={{border:'1px solid var(--border)',borderRadius:8,padding:'10px 10px 8px',background:'#fafafa',position:'relative'}}>
            <div style={{fontSize:11,fontWeight:700,color:'var(--muted)',textTransform:'uppercase',letterSpacing:.5,marginBottom:6}}>Leg {i + 1}</div>
            {legs.length > 1 && (
              <button style={{position:'absolute',top:8,right:8,background:'none',border:'none',color:'#cbd5e1',padding:0,cursor:'pointer',display:'inline-flex'}}
                      onClick={() => remove(leg.id)}><CloseIcon/></button>
            )}
            <InstrumentSearch value={leg.instrument} onSelect={ins => update(leg.id, 'instrument', ins)} />
            {leg.instrument && (
              <div style={{display:'grid',gridTemplateColumns:'80px 70px 1fr',gap:8}}>
                <div>
                  <label>Side</label>
                  <select value={leg.side} onChange={e => update(leg.id, 'side', e.target.value)}>
                    <option>BUY</option><option>SELL</option>
                  </select>
                </div>
                <div>
                  <label>{leg.instrument.instrument_type === 'EQ' ? 'Qty' : 'Lots'}</label>
                  <input type="number" min="1" placeholder="1" value={leg.lots}
                         onChange={e => update(leg.id, 'lots', e.target.value)} />
                </div>
                <div>
                  <label>Price</label>
                  <input type="number" step="0.05" placeholder="0.00" value={leg.price}
                         onChange={e => update(leg.id, 'price', e.target.value)} />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <button className="add-leg-btn" onClick={add}>
        <span className="add-leg-badge"><PlusIcon size={11}/></span>
        Add Leg
      </button>
    </div>
  )
}
