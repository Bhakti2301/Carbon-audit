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
    const processName = process?.name || entry.process_id || 'Activity'
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
      sourceName: activity?.name || entry.activity_id || factorDetail?.category_level_3 || 'Activity',
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

// Version 1 supports only the one reviewed end-to-end activity currently available
// in Firestore: UK DEFRA 2026 natural-gas consumption for power generation.
// It intentionally refuses unsupported frontend template activities rather than
// falling back to hardcoded factors in calc.js.
export async function requestCalculation(audit) {
  const catalog = await getCatalog()

  if (audit.facility?.country !== 'United Kingdom') {
    throw new Error('The currently imported DEFRA 2026 dataset supports UK reporting only. Select United Kingdom for this calculation.')
  }
  if (audit.factorSource !== 'DEFRA 2026') {
    throw new Error('Only the imported DEFRA 2026 factor dataset is available for live calculations in this version.')
  }
  if (audit.ipccFallback) {
    throw new Error('IPCC fallback is not available in this version. Turn off the fallback option and use the selected source only.')
  }

  const frameworks = {
    'GHG Protocol': 'ghg_protocol_corporate',
    'ISO 14064-1': 'iso_14064_1',
  }
  const accountingFramework = frameworks[audit.framework]
  if (!accountingFramework) {
    throw new Error('Select GHG Protocol or ISO 14064-1. The other framework options are not enabled in this backend version.')
  }

  if (audit.industryId !== 'power' || audit.subsectorId !== 'gasplant') {
    throw new Error('Live calculation is currently enabled only for Power Generation & Utilities → Gas-fired Power Plant → Gas Turbine Combustion.')
  }

  const allRows = audit.processes.flatMap((process) => process.rows.map((row) => ({ process, row })))
  if (!allRows.length) throw new Error('Add a natural-gas activity before calculating.')

  const industry = catalog.industries?.find((item) => item.id === 'power_generation')
  const process = industry?.processes?.find((item) => item.id === 'fuel_combustion')
  const activity = process?.activities?.find((item) => item.id === 'natural_gas_consumption')
  const factor = activity?.supported_factors?.find((item) =>
    item.source_id === 'defra_desnz' &&
    Number(item.dataset_year) === 2026 &&
    item.activity_unit === 'cubic metres' &&
    item.scope_number === 1
  )

  if (!activity?.factor_data_available || !factor) {
    throw new Error('The backend catalog did not return the approved natural-gas factor. Refresh the catalog or check the Flask service.')
  }

  for (const { process: uiProcess, row } of allRows) {
    if (uiProcess.name !== 'Gas Turbine Combustion' || row.sourceId !== 'natural_gas') {
      throw new Error('This version can calculate only natural-gas consumption in Gas Turbine Combustion. Remove other process or fuel entries before calculating.')
    }
    if (!['m³', 'm3', 'cubic metres'].includes(row.unit)) {
      throw new Error(`Natural gas currently supports cubic metres only. The selected unit '${row.unit}' is not supported by the approved factor.`)
    }
    if (Number(row.scope ?? 1) !== 1) {
      throw new Error('The approved natural-gas factor is classified as Scope 1. Use the suggested Scope 1 setting.')
    }
    if (!Number.isFinite(Number(row.qty)) || Number(row.qty) <= 0) {
      throw new Error('Enter a valid positive natural-gas quantity for every activity.')
    }
  }

  const reportingYear = String(audit.period?.end || audit.period?.start || '2026').slice(0, 4)
  if (!/^\d{4}$/.test(reportingYear)) throw new Error('Choose a valid reporting period.')

  const reportName = `${audit.facility.name.trim()} Carbon Audit (${audit.period.start} to ${audit.period.end})`.slice(0, 200)
  const created = await createReport({
    report_name: reportName,
    industry_id: 'power_generation',
    reporting_year: Number(reportingYear),
    factor_source_id: 'defra_desnz',
    factor_dataset_year: 2026,
    factor_dataset_id: factor.dataset_id,
    geography: 'UK',
    gwp_basis: 'source_defined',
    accounting_framework: accountingFramework,
    facility: audit.facility,
    period: audit.period,
    industry_name: industry.name,
    subsector_id: audit.subsectorId,
    subsector_name: 'Gas-fired Power Plant',
  })

  const completedSteps = []
  const byScope = { 1: 0, 2: 0, 3: 0 }
  for (const { process: uiProcess, row } of allRows) {
    let calculation
    try {
      calculation = await calculateAndLog({
        report_id: created.report_id,
        raw_value: Number(row.qty),
        selected_unit: 'cubic metres',
        process_id: 'fuel_combustion',
        activity_id: 'natural_gas_consumption',
        factor_id: factor.factor_id,
        user_name: 'Carbon Audit UI',
        declaration: row.evidence?.name || '',
        evidence_reference: row.evidence?.hash || '',
      })
    } catch (error) {
      throw new Error(`Report ${created.report_id} was created, but an activity could not be saved: ${error.message}. Open the report to inspect any entries already saved.`)
    }

    const detail = calculation.factor_details?.[0] || factor
    const scope = Number(calculation.scope) || 1
    const tco2e = Number(calculation.calculated_tco2e) || 0
    byScope[scope] += tco2e
    completedSteps.push({
      id: uiProcess.id,
      name: uiProcess.name,
      total: tco2e,
      rows: [{
        id: row.id,
        entryId: calculation.entry_id,
        sourceName: 'Natural gas',
        scope,
        factor: Number(detail.factor_value) / 1000,
        qty: Number(calculation.raw_value),
        unit: row.unit,
        tco2e,
        // The backend stores only the supplied evidence name/checksum reference;
        // it does not upload or retain the original file bytes.
        evidence: row.evidence || null,
        verified: null,
      }],
    })
  }

  const total = byScope[1] + byScope[2] + byScope[3]
  return {
    steps: completedSteps,
    byScope,
    total,
    reportId: created.report_id,
    reportName: created.report_name,
    calculationReady: created.calculation_ready,
  }
}
