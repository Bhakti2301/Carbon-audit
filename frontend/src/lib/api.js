const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5001').replace(/\/+$/, '')

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })

  let payload
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok || payload?.success === false) {
    const error = new Error(payload?.error || `API request failed (${response.status})`)
    error.status = response.status
    error.code = payload?.error_code || null
    throw error
  }

  return payload
}

let catalogPromise
export function getCatalog() {
  if (!catalogPromise) {
    catalogPromise = apiRequest('/api/catalog').catch((error) => {
      catalogPromise = null
      throw error
    })
  }
  return catalogPromise
}

export function getStandards() {
  return apiRequest('/api/standards')
}

export function createReport(payload) {
  return apiRequest('/api/reports', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function calculateAndLog(payload) {
  return apiRequest('/api/calculate-and-log', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

function frameworkLabel(id) {
  return ({
    ghg_protocol_corporate: 'GHG Protocol Corporate Standard',
    iso_14064_1: 'ISO 14064-1',
    pcaf: 'PCAF Financed Emissions',
  })[id] || id || '—'
}

function factorSourceLabel(id, catalog) {
  return catalog?.factor_sources?.find((source) => source.id === id)?.name || id || '—'
}

function locateCatalogActivity(catalog, industryId, processId, activityId) {
  const industry = catalog?.industries?.find((item) => item.id === industryId)
  const process = industry?.processes?.find((item) => item.id === processId)
  const activity = process?.activities?.find((item) => item.id === activityId)
  return { industry, process, activity }
}

// Readable name of a factor: its DEFRA category path, e.g.
// "Fuels · Gaseous fuels · Natural gas (100% mineral blend)".
export function factorLabel(factor) {
  return [
    factor?.category_level_1,
    factor?.category_level_2,
    factor?.category_level_3,
    factor?.category_level_4,
    factor?.column_text,
  ].filter(Boolean).join(' · ')
}

function summaryToDisplay(item, catalog) {
  const config = item.configuration || {}
  const totals = item.totals || {}
  const byScope = {
    1: Number(totals.scope_1 || 0),
    2: Number(totals.scope_2 || 0),
    3: Number(totals.scope_3 || 0),
  }
  const total = Number(totals.total ?? totals.total_tco2e ?? (byScope[1] + byScope[2] + byScope[3]))

  return {
    id: item.report_id,
    reportId: item.report_id,
    reportName: item.report_name || 'Untitled audit',
    status: item.status || 'Draft',
    createdAt: item.created_at || item.updated_at || null,
    facility: item.facility || {},
    period: item.period || {},
    industry: item.industry_name || item.industry_id || config.industry_id || '—',
    industryId: item.industry_id || config.industry_id || '',
    subsector: item.subsector_name || item.subsector_id || '—',
    framework: frameworkLabel(config.accounting_framework),
    factorSource: factorSourceLabel(config.factor_source_id, catalog),
    factorDatasetId: config.factor_dataset_id || null,
    factorDatasetYear: config.factor_dataset_year || null,
    factorDatasetRelease: config.factor_dataset_release || null,
    gridSource: 'Not separately configured',
    ipccFallback: false,
    configuration: config,
    totals: byScope,
    result: { total, byScope, steps: [] },
    emissionsUnit: item.emissions_unit || 'tCO2e',
  }
}

function detailToDisplay(report, catalog) {
  const display = summaryToDisplay(report, catalog)
  const configuration = report.configuration || report.raw_report?.configuration || {}
  const groups = new Map()
  const entries = Array.isArray(report.entries) ? report.entries : []
  const byScope = { 1: 0, 2: 0, 3: 0 }

  for (const entry of entries) {
    const { process, activity } = locateCatalogActivity(
      catalog,
      entry.industry_id || configuration.industry_id,
      entry.process_id,
      entry.activity_id,
    )
    const processName = entry.process_name || process?.name || entry.process_id || 'Activity'
    if (!groups.has(entry.process_id || processName)) {
      groups.set(entry.process_id || processName, { id: entry.process_id || processName, name: processName, rows: [], total: 0 })
    }

    const group = groups.get(entry.process_id || processName)
    const factorDetail = Array.isArray(entry.factor_details) ? entry.factor_details[0] : null
    const scope = Number(entry.scope) || Number(factorDetail?.scope) || 1
    const quantity = Number(entry.raw_value || 0)
    const tco2e = Number(entry.calculated_tco2e || 0)
    byScope[scope] = (byScope[scope] || 0) + tco2e
    group.total += tco2e
    group.rows.push({
      id: entry.entry_id || `${entry.process_id}-${group.rows.length + 1}`,
      entryId: entry.entry_id || '—',
      sourceName: entry.activity_name || activity?.name || factorLabel(factorDetail) || entry.activity_id || 'Activity',
      scope,
      factor: Number(factorDetail?.factor_value || 0) / 1000,
      qty: quantity,
      unit: entry.selected_unit || factorDetail?.activity_unit || '—',
      tco2e,
      evidence: entry.evidence?.declaration || entry.evidence?.reference
        ? {
            name: entry.evidence?.declaration || 'Evidence reference',
            hash: entry.evidence?.reference || '',
          }
        : null,
      // The backend response does not currently expose a persisted verification status.
      verified: null,
      factorDetails: entry.factor_details || [],
    })
  }

  const totals = report.totals || {}
  const savedByScope = {
    1: Number(totals.scope_1 ?? byScope[1] ?? 0),
    2: Number(totals.scope_2 ?? byScope[2] ?? 0),
    3: Number(totals.scope_3 ?? byScope[3] ?? 0),
  }
  const total = Number(totals.total ?? totals.total_tco2e ?? (savedByScope[1] + savedByScope[2] + savedByScope[3]))

  display.result = {
    steps: [...groups.values()],
    byScope: savedByScope,
    total,
    reportId: display.id,
  }
  display.entries = entries
  display.rawReport = report.raw_report || null
  return display
}

export async function fetchReports(limit = 100) {
  const payload = await apiRequest(`/api/reports?limit=${encodeURIComponent(limit)}`)
  const catalog = await getCatalog()
  return (payload.reports || []).map((item) => summaryToDisplay(item, catalog))
}

export async function fetchReportDetail(reportId) {
  const payload = await apiRequest(`/api/reports/${encodeURIComponent(reportId)}`)
  const catalog = await getCatalog()
  return detailToDisplay(payload.report, catalog)
}

export async function fetchReportsWithDetails(limit = 100) {
  const summaries = await fetchReports(limit)
  return Promise.all(summaries.map(async (summary) => {
    try {
      return await fetchReportDetail(summary.id)
    } catch (error) {
      console.warn(`Could not load detail for report ${summary.id}:`, error.message)
      return summary
    }
  }))
}

// ---------------------------------------------------------------------------
// Explicit factor selection
//
// The user searches the report's pinned DEFRA dataset through /api/factors and
// chooses one factor per activity entry. Industry, process and activity names
// are labels only: they never select or unlock a factor.
// ---------------------------------------------------------------------------

const FRAMEWORK_IDS = {
  'GHG Protocol': 'ghg_protocol_corporate',
  'ISO 14064-1': 'iso_14064_1',
}

// Guards for what the imported dataset can support, then the create-report body.
export function buildReportPayload(audit, meta = {}) {
  if (audit.facility?.country !== 'United Kingdom') {
    throw new Error('The currently imported DEFRA 2026 dataset supports UK reporting only. Select United Kingdom for this calculation.')
  }
  if (audit.factorSource !== 'DEFRA 2026') {
    throw new Error('Only the imported DEFRA 2026 factor dataset is available for live calculations in this version.')
  }
  if (audit.ipccFallback) {
    throw new Error('IPCC fallback is not available in this version. Turn off the fallback option and use the selected source only.')
  }
  const accountingFramework = FRAMEWORK_IDS[audit.framework]
  if (!accountingFramework) {
    throw new Error('Select GHG Protocol or ISO 14064-1. The other framework options are not enabled in this backend version.')
  }
  if (!audit.facility?.name?.trim() || !audit.period?.start || !audit.period?.end) {
    throw new Error('Enter the facility name and reporting period before choosing emission factors.')
  }
  const reportingYear = String(audit.period.end || audit.period.start).slice(0, 4)
  if (!/^\d{4}$/.test(reportingYear)) throw new Error('Choose a valid reporting period.')

  const industryName = (meta.industryName || '').trim()
  return {
    report_name: `${audit.facility.name.trim()} Carbon Audit (${audit.period.start} to ${audit.period.end})`.slice(0, 200),
    // Free-text label; any industry (predefined or custom) is accepted.
    industry_id: (meta.industryId || industryName || 'unspecified').slice(0, 100),
    industry_name: industryName,
    reporting_year: Number(reportingYear),
    factor_source_id: 'defra_desnz',
    factor_dataset_year: 2026,
    geography: 'UK',
    gwp_basis: 'source_defined',
    accounting_framework: accountingFramework,
    facility: audit.facility,
    period: audit.period,
    subsector_id: audit.subsectorId || '',
    subsector_name: (meta.subsectorName || '').trim(),
  }
}

// Two audits with the same signature can share one draft report.
export const reportSignature = (audit, meta) => JSON.stringify(buildReportPayload(audit, meta))

export const createDraftReport = (audit, meta) => createReport(buildReportPayload(audit, meta))

// Lists candidates from the report's pinned dataset. A candidate is NOT assumed
// to be applicable; the user must choose one.
export function searchFactors(reportId, { q = '', unit = '', scope = '', limit = 50 } = {}) {
  const params = new URLSearchParams({ report_id: reportId, limit: String(limit) })
  if (q.trim()) params.set('q', q.trim())
  if (unit) params.set('unit', unit)
  if (scope) params.set('scope', String(scope))
  return apiRequest(`/api/factors?${params.toString()}`)
}

// The minimum a row needs to remember about the factor the user chose.
export function toChosenFactor(candidate) {
  return {
    factor_id: candidate.factor_id,
    dataset_id: candidate.dataset_id,
    dataset_release: candidate.dataset_release || candidate.source_release,
    dataset_year: candidate.dataset_year,
    activity_unit: candidate.activity_unit,
    scope_number: Number(candidate.scope_number),
    factor_value: candidate.factor_value,
    ghg_unit: candidate.ghg_unit,
    geography: candidate.geography,
    source_name: candidate.source_name,
    label: factorLabel(candidate),
  }
}

// Calculates every entry with the factor the user chose for it. `report` is the
// draft report returned by createDraftReport (one report per calculation run).
export async function requestCalculation(audit, { report } = {}) {
  if (!report?.report_id) throw new Error('No report is available for this calculation. Try again.')

  const allRows = audit.processes.flatMap((process) => process.rows.map((row) => ({ process, row })))
  if (!allRows.length) throw new Error('Add at least one activity entry before calculating.')

  for (const { row } of allRows) {
    if (!row.factor?.factor_id) {
      throw new Error('Choose an emission factor for every activity entry before calculating.')
    }
    if (!Number.isFinite(Number(row.qty)) || Number(row.qty) <= 0) {
      throw new Error('Enter a valid positive quantity for every activity entry.')
    }
  }

  const groups = new Map()
  const byScope = { 1: 0, 2: 0, 3: 0 }

  for (const { process: uiProcess, row } of allRows) {
    let calculation
    try {
      calculation = await calculateAndLog({
        report_id: report.report_id,
        raw_value: Number(row.qty),
        // Unit, scope and release come from the chosen factor, and the backend
        // re-validates all of them against the report's pinned dataset.
        selected_unit: row.factor.activity_unit,
        factor_id: row.factor.factor_id,
        dataset_id: row.factor.dataset_id,
        dataset_release: row.factor.dataset_release,
        scope: row.factor.scope_number,
        // Labels only; any wording is accepted.
        process_name: uiProcess.name,
        activity_name: row.factor.label,
        user_name: 'Carbon Audit UI',
        declaration: row.evidence?.name || '',
        evidence_reference: row.evidence?.hash || '',
      })
    } catch (error) {
      throw new Error(`Report ${report.report_id} was created, but an activity could not be saved: ${error.message}. Open the report to inspect any entries already saved.`)
    }

    const detail = calculation.factor_details?.[0] || row.factor
    const scope = Number(calculation.scope) || row.factor.scope_number || 1
    const tco2e = Number(calculation.calculated_tco2e) || 0
    byScope[scope] += tco2e

    if (!groups.has(uiProcess.id)) groups.set(uiProcess.id, { id: uiProcess.id, name: uiProcess.name, total: 0, rows: [] })
    const group = groups.get(uiProcess.id)
    group.total += tco2e
    group.rows.push({
      id: row.id,
      entryId: calculation.entry_id,
      sourceName: row.factor.label,
      scope,
      factor: Number(detail.factor_value) / 1000,
      qty: Number(calculation.raw_value),
      unit: row.factor.activity_unit,
      tco2e,
      // The backend stores only the supplied evidence name/checksum reference;
      // it does not upload or retain the original file bytes.
      evidence: row.evidence || null,
      verified: null,
    })
  }

  return {
    steps: [...groups.values()],
    byScope,
    total: byScope[1] + byScope[2] + byScope[3],
    reportId: report.report_id,
    reportName: report.report_name,
    calculationReady: report.calculation_ready,
  }
}
