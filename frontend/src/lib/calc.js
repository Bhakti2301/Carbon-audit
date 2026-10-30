import { SOURCES, COUNTRIES } from '../data/catalog.js'

// Scope 2 electricity uses the facility country's grid factor; everything else
// uses the source's default factor. Falls back to India when country is unknown.
export function factorFor(sourceId, unit, country) {
  const source = SOURCES[sourceId]
  if (!source) return 0
  if (sourceId === 'grid_electricity') {
    const perMWh = (COUNTRIES[country] ?? COUNTRIES.India).gridFactor
    return unit === 'kWh' ? perMWh / 1000 : perMWh
  }
  return source.units[unit] ?? 0
}

export const effectiveScope = (row) => row.scope ?? SOURCES[row.sourceId]?.scope ?? 1

// Pure calculation: quantity × emission factor, summed per process and per scope.
export function calculateAudit(processes, country) {
  const byScope = { 1: 0, 2: 0, 3: 0 }

  const processResults = processes.map((p) => {
    const rows = p.rows.map((row) => {
      const source = SOURCES[row.sourceId]
      const factor = factorFor(row.sourceId, row.unit, country)
      const qty = Number(row.qty) || 0
      const tco2e = qty * factor
      const scope = effectiveScope(row)
      byScope[scope] += tco2e
      return {
        id: row.id, entryId: row.entryId, unit: row.unit, evidence: row.evidence, verified: row.verified,
        sourceName: source?.name ?? '—', scope, factor, qty, tco2e,
      }
    })
    const total = rows.reduce((sum, r) => sum + r.tco2e, 0)
    return { id: p.id, name: p.name, rows, total }
  })

  const total = processResults.reduce((sum, s) => sum + s.total, 0)
  return { steps: processResults, byScope, total }
}

export function fmt(n, digits = 1) {
  return Number(n || 0).toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function fmtFactor(n) {
  return Number(n).toLocaleString('en-IN', { maximumSignificantDigits: 4 })
}

export function fmtDate(isoDate) {
  if (!isoDate) return '—'
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export const fmtPeriod = (p) => (p ? `${fmtDate(p.start)} – ${fmtDate(p.end)}` : '—')

export async function sha256(buffer) {
  const digest = await crypto.subtle.digest('SHA-256', buffer)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}
