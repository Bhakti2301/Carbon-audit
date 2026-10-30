import { useEffect, useMemo, useState } from 'react'
import Icon from '../components/Icon.jsx'
import { loadTarget, saveTarget } from '../lib/storage.js'
import { fmt, fmtPeriod } from '../lib/calc.js'
import { fetchReportsWithDetails } from '../lib/api.js'
import { navigate } from '../App.jsx'

const SCOPE_COLOR = { 1: 'var(--c-s1)', 2: 'var(--c-s2)', 3: 'var(--c-s3)' }
const SCOPE_NAME = { 1: 'Scope 1 · direct', 2: 'Scope 2 · electricity', 3: 'Scope 3 · value chain' }

function Donut({ byScope, total }) {
  const radius = 70
  const circumference = 2 * Math.PI * radius
  let offset = 0
  return (
    <svg viewBox="0 0 180 180" className="donut" role="img" aria-label="Emissions by scope">
      <circle cx="90" cy="90" r={radius} fill="none" stroke="var(--track)" strokeWidth="22" />
      {[1, 2, 3].map((scope) => {
        const length = total > 0 ? (byScope[scope] / total) * circumference : 0
        if (length <= 0) return null
        const element = <circle key={scope} cx="90" cy="90" r={radius} fill="none" stroke={SCOPE_COLOR[scope]} strokeWidth="22"
          strokeDasharray={`${Math.max(length - 2, 0.5)} ${circumference}`} strokeDashoffset={-offset} transform="rotate(-90 90 90)" />
        offset += length
        return element
      })}
      <text x="90" y="86" textAnchor="middle" className="donut-num">{fmt(total, 2)}</text>
      <text x="90" y="106" textAnchor="middle" className="donut-unit">tCO₂e</text>
    </svg>
  )
}

function Gauge({ value, target }) {
  const pct = target > 0 ? Math.min(value / target, 1.2) : 0
  const angle = Math.PI * (1 - Math.min(pct, 1))
  const radius = 80
  const x = 100 + radius * Math.cos(angle)
  const y = 100 - radius * Math.sin(angle)
  const over = value > target
  return (
    <svg viewBox="0 0 200 116" className="gauge" role="img" aria-label={`${Math.round(pct * 100)}% of target`}>
      <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="var(--track)" strokeWidth="16" strokeLinecap="round" />
      {pct > 0 && <path d={`M20 100 A80 80 0 0 1 ${x.toFixed(2)} ${y.toFixed(2)}`} fill="none" stroke={over ? 'var(--red)' : 'var(--brand)'} strokeWidth="16" strokeLinecap="round" />}
      <text x="100" y="92" textAnchor="middle" className="donut-num">{Math.round((value / (target || 1)) * 100)}%</text>
      <text x="100" y="110" textAnchor="middle" className="donut-unit">of target used</text>
    </svg>
  )
}

export default function DashboardPage() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [facility, setFacility] = useState('all')
  const [range, setRange] = useState('all')
  const [target, setTarget] = useState(loadTarget)

  useEffect(() => {
    let cancelled = false
    fetchReportsWithDetails()
      .then((items) => { if (!cancelled) setReports(items) })
      .catch((err) => { if (!cancelled) setError(err.message || 'Unable to load dashboard data.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const facilities = [...new Set(reports.map((report) => report.facility?.name).filter(Boolean))]
  const years = [...new Set(reports.map((report) => report.period?.start?.slice(0, 4)).filter(Boolean))].sort()
  const shown = useMemo(() => reports.filter((report) =>
    (facility === 'all' || report.facility?.name === facility) &&
    (range === 'all' || report.period?.start?.startsWith(range))), [reports, facility, range])

  const stats = useMemo(() => {
    const byScope = { 1: 0, 2: 0, 3: 0 }
    const activities = {}
    let entries = 0
    for (const report of shown) {
      for (const scope of [1, 2, 3]) byScope[scope] += Number(report.result?.byScope?.[scope] || 0)
      for (const process of report.result?.steps || []) {
        for (const row of process.rows || []) {
          const key = `${process.name} · ${row.sourceName}`
          activities[key] ||= { name: process.name, source: row.sourceName, scope: row.scope, total: 0 }
          activities[key].total += Number(row.tco2e || 0)
          entries += 1
        }
      }
    }
    const total = byScope[1] + byScope[2] + byScope[3]
    const top = Object.values(activities).sort((a, b) => b.total - a.total).slice(0, 5)
    const trend = [...shown].sort((a, b) => String(a.period?.start || '').localeCompare(String(b.period?.start || '')))
    return { byScope, total, top, trend, entries }
  }, [shown])

  const changeTarget = (value) => {
    const next = Math.max(0, Number(value) || 0)
    setTarget(next)
    saveTarget(next)
  }

  if (loading) return <><div className="top"><b>Dashboard</b></div><main className="main"><div className="card empty-card"><p>Loading saved emissions data…</p></div></main></>
  if (error) return <><div className="top"><b>Dashboard</b></div><main className="main"><div className="card empty-card"><h3>Dashboard data unavailable</h3><p>{error}</p><button className="btn" onClick={() => window.location.reload()}>Retry</button></div></main></>

  if (reports.length === 0) {
    return (
      <>
        <div className="top"><b>Dashboard</b></div>
        <main className="main">
          <div className="page-head"><div><h1>Dashboard</h1><p className="sub">Emissions across your saved Carbon Audit reports.</p></div></div>
          <div className="card empty-card">
            <h3>No saved reports yet</h3>
            <p>The dashboard now reads from the backend. Create and calculate a supported audit to see real results here.</p>
            <div className="head-actions"><button className="btn p" onClick={() => navigate('/audit')}>New audit</button><button className="btn" onClick={() => navigate('/reports')}>View reports</button></div>
          </div>
        </main>
      </>
    )
  }

  const topMax = Math.max(...stats.top.map((item) => item.total), 0.0001)
  const trendMax = Math.max(...stats.trend.map((report) => report.result?.total || 0), 0.0001)

  return (
    <>
      <div className="top"><b>Dashboard</b></div>
      <main className="main">
        <div className="page-head">
          <div><h1>Dashboard</h1><p className="sub">{shown.length} {shown.length === 1 ? 'report' : 'reports'} · {stats.entries} saved activity entries</p></div>
          <div className="head-actions filters">
            <select aria-label="Facility" value={facility} onChange={(event) => setFacility(event.target.value)}><option value="all">All facilities</option>{facilities.map((name) => <option key={name}>{name}</option>)}</select>
            <select aria-label="Reporting year" value={range} onChange={(event) => setRange(event.target.value)}><option value="all">All periods</option>{years.map((year) => <option key={year} value={year}>Starting {year}</option>)}</select>
          </div>
        </div>

        <div className="kpis">
          <div className="card kpi"><span>Total emissions</span><b>{fmt(stats.total, 2)}</b><small>tCO₂e</small></div>
          {[1, 2, 3].map((scope) => <div className="card kpi" key={scope}><span><i className="dot" style={{ background: SCOPE_COLOR[scope] }} />{SCOPE_NAME[scope]}</span><b>{fmt(stats.byScope[scope], 2)}</b><small>{stats.total ? Math.round((stats.byScope[scope] / stats.total) * 100) : 0}% of total</small></div>)}
        </div>

        <div className="dash-grid">
          <section className="card"><div className="ch"><h3>Emissions by scope</h3></div><div className="cb donut-wrap"><Donut byScope={stats.byScope} total={stats.total} /><ul className="legend">{[1, 2, 3].map((scope) => <li key={scope}><i className="dot" style={{ background: SCOPE_COLOR[scope] }} /><span>{SCOPE_NAME[scope]}</span><b>{fmt(stats.byScope[scope], 2)} t</b></li>)}</ul></div></section>
          <section className="card"><div className="ch"><h3>Against target</h3><p>Target is a local display preference</p></div><div className="cb gauge-wrap"><Gauge value={stats.total} target={target} /><div className="gauge-meta"><div><span>Emitted</span><b>{fmt(stats.total, 2)} t</b></div><div><label htmlFor="target">Target (tCO₂e)</label><input id="target" type="number" min="0" value={target} onChange={(event) => changeTarget(event.target.value)} /></div></div></div></section>
        </div>

        <section className="card"><div className="ch"><h3>Top 5 emitting activities</h3><p>Based on saved backend calculation entries</p></div>
          {stats.top.length === 0 ? <div className="cb empty">No calculation entries are available yet.</div> : <div className="bars">{stats.top.map((item) => <div className="br top5" key={`${item.name}-${item.source}`}><span className="br-name">{item.name}<span className="cell-sub">{item.source}</span></span><div className="trk"><div className="fill" style={{ width: `${(item.total / topMax) * 100}%`, background: SCOPE_COLOR[item.scope] || 'var(--brand)' }} /></div><span className="br-val">{fmt(item.total, 2)} tCO₂e</span></div>)}</div>}
        </section>

        <section className="card"><div className="ch"><h3>Trend by reporting period</h3><p>Total tCO₂e per saved report</p></div><div className="cb"><div className="cols" role="img" aria-label="Emissions per reporting period">{stats.trend.map((report) => <button key={report.id} className="col" onClick={() => navigate(`/reports/${report.id}`)}><span className="col-val">{fmt(report.result?.total || 0, 2)}</span><span className="col-bar" style={{ height: `${((report.result?.total || 0) / trendMax) * 160}px` }} /><span className="col-lbl">{report.period?.start ? new Date(`${report.period.start}T00:00:00`).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }) : report.id}</span></button>)}</div></div></section>

        <div className="dash-foot"><span className="footnote">Dashboard values are loaded from saved backend reports. The target value is stored locally in this browser.</span><span className="head-actions"><button className="btn ghost sm" onClick={() => navigate('/reports')}><Icon name="file" size={16} />All reports</button><button className="btn p sm" onClick={() => navigate('/audit')}>New audit</button></span></div>
      </main>
    </>
  )
}
