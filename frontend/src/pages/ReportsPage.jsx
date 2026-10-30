import { useEffect, useState } from 'react'
import Icon from '../components/Icon.jsx'
import { fmt, fmtPeriod } from '../lib/calc.js'
import { fetchReports } from '../lib/api.js'
import { navigate } from '../App.jsx'

export default function ReportsPage() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchReports()
      .then((items) => { if (!cancelled) setReports(items) })
      .catch((err) => { if (!cancelled) setError(err.message || 'Unable to load reports from the backend.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <>
      <div className="top"><b>Reports</b></div>
      <main className="main">
        <div className="page-head">
          <div>
            <h1>Reports</h1>
            <p className="sub">Carbon reports saved by the Carbon Audit backend.</p>
          </div>
          <div className="head-actions">
            <button className="btn p" onClick={() => navigate('/audit')}><Icon name="plus" size={16} />New audit</button>
          </div>
        </div>

        {loading && <div className="card empty-card"><p>Loading saved reports…</p></div>}
        {error && <div className="card empty-card"><h3>Couldn't load reports</h3><p>{error}</p><button className="btn" onClick={() => window.location.reload()}>Retry</button></div>}
        {!loading && !error && reports.length === 0 && (
          <div className="card empty-card">
            <h3>Start your first carbon audit</h3>
            <p>Reports will appear here after an audit is calculated and saved by the backend.</p>
            <button className="btn p" onClick={() => navigate('/audit')}>New audit</button>
          </div>
        )}
        {!loading && !error && reports.length > 0 && (
          <div className="card table-wrap">
            <table className="tbl">
              <thead>
                <tr><th>Report ID</th><th>Facility</th><th>Industry</th><th>Reporting period</th><th>Framework</th><th>Status</th><th className="num-col">Total (tCO₂e)</th><th>Created</th></tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id} className="clickable" onClick={() => navigate(`/reports/${r.id}`)}>
                    <td><a href={`#/reports/${encodeURIComponent(r.id)}`} onClick={(event) => event.stopPropagation()}>{r.id}</a></td>
                    <td>{r.facility?.name || '—'}<div className="cell-sub">{[r.facility?.city, r.facility?.country].filter(Boolean).join(', ') || 'Location not provided'}</div></td>
                    <td>{r.industry || '—'}<div className="cell-sub">{r.subsector || ''}</div></td>
                    <td>{fmtPeriod(r.period)}<div className="cell-sub">{r.period?.type || ''}</div></td>
                    <td>{r.framework}<div className="cell-sub">{r.factorSource}</div></td>
                    <td>{r.status || 'Draft'}</td>
                    <td className="num-col">{fmt(r.result?.total, 2)}</td>
                    <td>{r.createdAt ? new Date(r.createdAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </>
  )
}
