// Browser storage until the backend database exists.
// v2 keys: the audit shape changed (facility address, period, processes).
const REPORTS_KEY = 'carbonledger.v2.reports'
const DRAFT_KEY = 'carbonledger.v2.draft'
const INDUSTRIES_KEY = 'carbonledger.v2.customIndustries'
const TARGET_KEY = 'carbonledger.v2.target'

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

export const loadReports = () => read(REPORTS_KEY, [])

export function saveReport(report) {
  const reports = loadReports()
  const year = new Date().getFullYear()
  const id = `RPT-${year}-${String(reports.length + 1).padStart(3, '0')}`
  const saved = { ...report, id, createdAt: new Date().toISOString() }
  write(REPORTS_KEY, [saved, ...reports])
  return saved
}

export const saveReports = (reports) => write(REPORTS_KEY, reports)

export function deleteReport(id) {
  write(REPORTS_KEY, loadReports().filter((r) => r.id !== id))
}

export const loadDraft = () => read(DRAFT_KEY, null)
export const saveDraft = (draft) => write(DRAFT_KEY, draft)
export const clearDraft = () => {
  try {
    localStorage.removeItem(DRAFT_KEY)
  } catch {}
}

export const loadCustomIndustries = () => read(INDUSTRIES_KEY, [])
export const saveCustomIndustries = (list) => write(INDUSTRIES_KEY, list)

export const loadTarget = () => read(TARGET_KEY, 2000)
export const saveTarget = (t) => write(TARGET_KEY, t)
