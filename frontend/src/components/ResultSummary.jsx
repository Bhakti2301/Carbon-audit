import { fmt } from '../lib/calc.js'

const SCOPE_LABEL = { 1: 'Direct (fuel burnt on site)', 2: 'Purchased electricity', 3: 'Value chain' }

export function ScopeTag({ scope }) {
  return <span className={`tag s${scope}`}>Scope {scope}</span>
}

export default function ResultSummary({ result }) {
  const max = Math.max(...result.steps.map((s) => s.total), 0.0001)

  return (
    <div className="res">
      <div className="tot">
        <div className="muted-label">Total emissions</div>
        <div className="big">
          {fmt(result.total)}<small>tCO₂e</small>
        </div>
        <div className="scopes">
          {[1, 2, 3]
            .filter((s) => result.byScope[s] > 0 || s < 3)
            .map((s) => (
              <div className="sc" key={s}>
                <span><ScopeTag scope={s} /> {SCOPE_LABEL[s]}</span>
                <b>{fmt(result.byScope[s])} t</b>
              </div>
            ))}
        </div>
      </div>
      <div className="bars">
        <div className="muted-label">By process / activity</div>
        {result.steps.map((s) => (
          <div className="br" key={s.id}>
            <span className="br-name">{s.name}</span>
            <div className="trk"><div className="fill" style={{ width: `${(s.total / max) * 100}%` }} /></div>
            <span className="br-val">{fmt(s.total)} tCO₂e</span>
          </div>
        ))}
      </div>
    </div>
  )
}
