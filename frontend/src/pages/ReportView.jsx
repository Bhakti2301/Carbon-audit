
import { useEffect, useState } from 'react'
import Icon from '../components/Icon.jsx'
import ResultSummary, { ScopeTag } from '../components/ResultSummary.jsx'
import { fetchReportDetail } from '../lib/api.js'
import { fmt, fmtFactor, fmtPeriod } from '../lib/calc.js'
import { navigate } from '../App.jsx'

export default function ReportView({ id }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadReport() {
      setLoading(true)
      setError('')
      setReport(null)

      try {
        if (!id) {
          throw new Error('No report ID was provided.')
        }

        const data = await fetchReportDetail(id)

        if (!data) {
          throw new Error('The backend returned no report data.')
        }

        if (!cancelled) {
          setReport(data)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Unable to load this report.')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadReport()

    return () => {
      cancelled = true
    }
  }, [id])

  if (loading) {
    return (
      <main className="main">
        <div className="card empty-card">
          <p>Loading report…</p>
        </div>
      </main>
    )
  }

  if (error || !report) {
    return (
      <main className="main">
        <div className="card empty-card">
          <h3>Report could not be loaded</h3>
          <p>{error || 'The requested report was not returned by the backend.'}</p>
          <button className="btn" onClick={() => navigate('/reports')}>
            Back to reports
          </button>
        </div>
      </main>
    )
  }

  const facility = report.facility || {}
  const result = report.result || {}
  const steps = Array.isArray(result.steps) ? result.steps : []

  const createdAt = report.updatedAt || report.createdAt

  const created = createdAt
    ? new Date(createdAt).toLocaleString('en-GB', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '—'

  const address = [
    facility.address,
    facility.city,
    facility.state,
    facility.pincode,
    facility.country,
  ]
    .filter(Boolean)
    .join(', ')

  const datasetLabel = [
    report.factorDatasetYear,
    report.factorDatasetRelease
      ? `release ${report.factorDatasetRelease}`
      : '',
  ]
    .filter(Boolean)
    .join(' · ')

  const total = Number(
    result.total ??
    ((Number(result.byScope?.[1]) || 0) +
      (Number(result.byScope?.[2]) || 0) +
      (Number(result.byScope?.[3]) || 0))
  )

  return (
    <>
      <div className="top no-print">
        <a href="#/reports">Reports</a>
        <span className="sep"> / </span>
        <b>{report.id || id}</b>
      </div>

      <main className="main">
        <div className="page-head">
          <div>
            <div className="title-row">
              <h1>Carbon emission report</h1>
              <span className="badge">{report.id || id}</span>
            </div>

            <p className="sub">
              {facility.name || 'Unnamed facility'}
              {' · '}
              {facility.city || 'Location not provided'}
              {' · '}
              {fmtPeriod(report.period)}
            </p>
          </div>

          <div className="head-actions no-print">
            <button
              className="btn ghost"
              onClick={() => navigate('/reports')}
            >
              <Icon name="back" size={16} />
              Back
            </button>

            <button
              className="btn p"
              onClick={() => window.print()}
            >
              <Icon name="print" size={16} />
              Print / save PDF
            </button>
          </div>
        </div>

        <section className="card">
          <div className="cb meta">
            <div>
              <span>Facility</span>
              <b>{facility.name || '—'}</b>
            </div>

            <div>
              <span>Facility type</span>
              <b>{facility.type || '—'}</b>
            </div>

            <div className="span2">
              <span>Address</span>
              <b>{address || '—'}</b>
            </div>

            <div>
              <span>Industry</span>
              <b>{report.industry || '—'}</b>
            </div>

            <div>
              <span>Sub-sector</span>
              <b>{report.subsector || '—'}</b>
            </div>

            <div>
              <span>Reporting period</span>
              <b>
                {fmtPeriod(report.period)}
                {report.period?.type
                  ? ` (${report.period.type})`
                  : ''}
              </b>
            </div>

            <div>
              <span>Framework</span>
              <b>{report.framework || '—'}</b>
            </div>

            <div>
              <span>Factor source</span>
              <b>{report.factorSource || '—'}</b>
            </div>

            <div>
              <span>Dataset</span>
              <b>
                {datasetLabel || report.factorDatasetId || '—'}
              </b>
            </div>

            <div>
              <span>Geography</span>
              <b>{report.configuration?.geography || '—'}</b>
            </div>

            <div>
              <span>Coordinates</span>
              <b>
                {facility.lat && facility.lng
                  ? `${facility.lat}, ${facility.lng}`
                  : '—'}
              </b>
            </div>

            <div>
              <span>Status</span>
              <b>{report.status || 'Draft'}</b>
            </div>

            <div>
              <span>Last updated</span>
              <b>{created}</b>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="ch">
            <h3>Summary</h3>
          </div>

          <ResultSummary
            result={{
              ...result,
              total,
              byScope: result.byScope || {
                1: 0,
                2: 0,
                3: 0,
              },
            }}
          />
        </section>

        <section className="card table-wrap">
          <div className="ch">
            <h3>Calculation detail</h3>
            <p>
              Emissions = activity quantity × source factor,
              converted to tCO₂e
            </p>
          </div>

          <table className="tbl">
            <thead>
              <tr>
                <th>Entry</th>
                <th>Process / activity</th>
                <th>Fuel / energy</th>
                <th>Scope</th>
                <th className="num-col">Quantity</th>
                <th>Unit</th>
                <th className="num-col">Factor (tCO₂e/unit)</th>
                <th className="num-col">Emissions (tCO₂e)</th>
                <th>Evidence reference</th>
                <th>Status</th>
              </tr>
            </thead>

            <tbody>
              {steps.flatMap((step, stepIndex) => {
                const rows = Array.isArray(step.rows) ? step.rows : []

                return rows.map((row, rowIndex) => (
                  <tr
                    key={
                      row.id ||
                      row.entryId ||
                      `${stepIndex}-${rowIndex}`
                    }
                  >
                    <td className="mono">
                      {row.entryId || '—'}
                    </td>

                    <td>
                      {rowIndex === 0 ? step.name || 'Activity' : ''}
                    </td>

                    <td>{row.sourceName || '—'}</td>

                    <td>
                      <ScopeTag scope={row.scope || 1} />
                    </td>

                    <td className="num-col">
                      {Number.isFinite(Number(row.qty))
                        ? Number(row.qty).toLocaleString('en-GB', {
                            maximumFractionDigits: 3,
                          })
                        : '—'}
                    </td>

                    <td>{row.unit || '—'}</td>

                    <td className="num-col">
                      {Number.isFinite(Number(row.factor))
                        ? fmtFactor(row.factor)
                        : '—'}
                    </td>

                    <td className="num-col">
                      {fmt(row.tco2e, 6)}
                    </td>

                    <td>
                      {row.evidence ? (
                        <>
                          {row.evidence.name || 'Evidence reference'}

                          {row.evidence.hash && (
                            <div className="cell-sub mono">
                              SHA-256 {row.evidence.hash.slice(0, 12)}…
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="cell-sub">None</span>
                      )}
                    </td>

                    <td>
                      <span className="status">
                        Saved · not independently verified
                      </span>
                    </td>
                  </tr>
                ))
              })}

              <tr className="total-row">
                <td colSpan={7}>Total</td>
                <td className="num-col">{fmt(total, 6)}</td>
                <td colSpan={2} />
              </tr>
            </tbody>
          </table>

          {steps.length === 0 && (
            <p className="footnote">
              No calculation entries have been saved to this report yet.
            </p>
          )}
        </section>

        <p className="footnote">
          Calculation results and factor provenance are loaded from
          the backend. The imported DEFRA 2026 factor dataset is
          UK-specific; other geographies require an applicable
          factor dataset and reviewed mappings.
        </p>
      </main>
    </>
  )
}
