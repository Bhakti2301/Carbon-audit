import { useMemo, useRef, useState } from 'react'
import Icon from '../components/Icon.jsx'
import ResultSummary, { ScopeTag } from '../components/ResultSummary.jsx'
import {
  INDUSTRIES, SOURCES, ALL_SOURCE_IDS, FRAMEWORKS, FACTOR_SOURCES, COUNTRIES, FACILITY_TYPES, PERIOD_TYPES,
} from '../data/catalog.js'
import { requestCalculation, createDraftReport, reportSignature, searchFactors, toChosenFactor, factorLabel } from '../lib/api.js'
import { effectiveScope, sha256, fmtPeriod } from '../lib/calc.js'
import {
  loadDraft, saveDraft, clearDraft, loadCustomIndustries, saveCustomIndustries,
} from '../lib/storage.js'
import { navigate } from '../App.jsx'

const uid = () => Math.random().toString(36).slice(2, 10)
const firstUnit = (sourceId) => Object.keys(SOURCES[sourceId].units)[0]

// Every activity entry gets a unique ID so evidence and approvals can be traced to it.
function newRow(a, sourceId) {
  const entryId = `ACT-${String(a.nextEntry++).padStart(3, '0')}`
  return { id: uid(), entryId, sourceId, qty: '', unit: firstUnit(sourceId), scope: null, factor: null, evidence: null, verified: null, reset: false }
}
const newProcess = (a, process) => ({ id: uid(), name: process.name, rows: [newRow(a, process.sources[0])] })

const iso = (d) => d.toISOString().slice(0, 10)
function periodEnd(type, start) {
  if (!start || type === 'Custom') return ''
  const months = { Monthly: 1, Quarterly: 3, Annual: 12 }[type]
  const d = new Date(`${start}T00:00:00Z`)
  d.setUTCMonth(d.getUTCMonth() + months)
  d.setUTCDate(d.getUTCDate() - 1)
  return iso(d)
}

const emptyAudit = () => ({
  facility: { name: '', type: FACILITY_TYPES[0], address: '', city: '', state: '', country: 'United Kingdom', pincode: '', lat: '', lng: '' },
  period: { type: 'Annual', start: '2025-04-01', end: '2026-03-31' },
  framework: 'GHG Protocol',
  factorSource: 'DEFRA 2026',
  ipccFallback: false,
  industryId: '',
  subsectorId: '',
  customSubsector: '',
  processes: [],
  nextEntry: 1,
  history: [],
})

function sampleAudit() {
  const a = emptyAudit()
  a.facility = {
    name: 'UK Gas Power Demo', type: 'Company / plant', address: 'Example Road', city: 'London',
    state: 'Greater London', country: 'United Kingdom', pincode: '', lat: '', lng: '',
  }
  a.industryId = 'power'
  a.subsectorId = 'gasplant'
  const power = INDUSTRIES.find((item) => item.id === 'power')
  const gasPlant = power?.subsectors.find((item) => item.id === 'gasplant')
  const gasProcess = gasPlant?.processes.find((item) => item.name === 'Gas Turbine Combustion')
  if (gasProcess) {
    const process = newProcess(a, gasProcess)
    process.rows[0] = { ...process.rows[0], qty: '100', unit: 'm³' }
    a.processes = [process]
    a.nextEntry = 2
  }
  return a
}

// Short search hints only. They prefill the search box; they never choose a factor.
const SEARCH_HINT = {
  natural_gas: 'natural gas', diesel: 'diesel', petrol: 'petrol', coal: 'coal', coking_coal: 'coking',
  furnace_oil: 'fuel oil', lpg: 'lpg', jet_fuel: 'aviation', marine_fuel: 'marine', grid_electricity: 'electricity',
  refrigerant_r404a: 'r404', refrigerant_r134a: 'r134', urea: 'urea', air_travel: 'flight', truck_distance: 'hgv', van_distance: 'van',
}

const fmtValue = (n) => Number(n).toLocaleString('en-GB', { maximumSignificantDigits: 6 })

// The user searches the report's pinned dataset and picks one factor per entry.
// Nothing is chosen automatically and no candidate is assumed to be applicable.
function FactorPicker({ sourceId, selected, error, getReport, onChoose, onClear }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState(SEARCH_HINT[sourceId] ?? '')
  const [state, setState] = useState({ loading: false, error: '', results: null, total: 0 })

  const search = async (text) => {
    setState((prev) => ({ ...prev, loading: true, error: '' }))
    try {
      const report = await getReport()
      const data = await searchFactors(report.report_id, { q: text, limit: 50 })
      const results = data.factors || []
      setState({ loading: false, error: '', results, total: data.total_matches ?? results.length })
    } catch (e) {
      setState({ loading: false, error: e?.message || 'Could not load factor candidates.', results: null, total: 0 })
    }
  }

  const box = { border: '1px solid var(--track)', borderRadius: 8, padding: '10px 12px', margin: '2px 0 8px' }

  if (selected) {
    return (
      <div style={box}>
        <div><b>{selected.label}</b></div>
        <div className="cell-sub">
          {fmtValue(selected.factor_value)} kgCO₂e per {selected.activity_unit} · Scope {selected.scope_number} · {selected.geography} · {selected.source_name || 'DEFRA'} release {selected.dataset_release} · ID {selected.factor_id}
        </div>
        <button className="link hint" onClick={onClear}>Change factor</button>
      </div>
    )
  }

  if (!open) {
    return (
      <div style={box}>
        <button className="btn sm" onClick={() => { setOpen(true); search(query) }}>Choose emission factor</button>
        <span className="hint"> Required: pick the DEFRA factor that matches this activity.</span>
        {error && <div className="err">{error}</div>}
      </div>
    )
  }

  return (
    <div style={box}>
      <div className="addform">
        <input aria-label="Search emission factors" value={query} placeholder="e.g. natural gas, diesel, electricity"
          onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search(query)} />
        <button className="btn p sm" onClick={() => search(query)} disabled={state.loading}>{state.loading ? 'Searching…' : 'Search'}</button>
        <button className="btn ghost sm" onClick={() => setOpen(false)}>Close</button>
      </div>
      {state.error && <div className="err">{state.error}</div>}
      {state.results && state.results.length === 0 && <div className="hint">No factor matched. Try a shorter search.</div>}
      {state.results && state.results.length > 0 && (
        <>
          <div className="hint">
            {state.total > state.results.length ? `Showing ${state.results.length} of ${state.total} matches. Refine the search to narrow them. ` : `${state.results.length} candidate${state.results.length === 1 ? '' : 's'}. `}
            Candidates are not checked against your activity; choose the one that applies.
          </div>
          {state.results.map((f) => (
            <div key={f.factor_id} style={{ display: 'flex', gap: 12, alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid var(--track)' }}>
              <div>
                <div><b>{factorLabel(f)}</b></div>
                <div className="cell-sub">{fmtValue(f.factor_value)} kgCO₂e per {f.activity_unit} · Scope {f.scope_number} · release {f.dataset_release} · {f.geography}</div>
              </div>
              <button className="btn sm" onClick={() => { onChoose(toChosenFactor(f)); setOpen(false) }}>Use this factor</button>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

function validate(audit, isCustom) {
  const e = {}
  const f = audit.facility
  if (!f.name.trim()) e['facility.name'] = 'Enter the facility name'
  if (!f.address.trim()) e['facility.address'] = 'Enter the street address'
  if (!f.city.trim()) e['facility.city'] = 'Enter the city'
  if (!audit.period.start) e['period.start'] = 'Pick a start date'
  if (!audit.period.end) e['period.end'] = 'Pick an end date'
  else if (audit.period.end < audit.period.start) e['period.end'] = 'End date must be after the start date'
  if (!audit.industryId) e.industry = 'Choose an industry'
  else if (isCustom ? !audit.customSubsector.trim() : !audit.subsectorId) e.subsector = 'Enter a sub-sector'
  else if (audit.processes.length === 0) e.processes = 'Add at least one process / activity'
  audit.processes.forEach((p) => {
    if (p.rows.length === 0) e[`proc.${p.id}`] = 'Add at least one fuel or energy entry'
    p.rows.forEach((row) => {
      const q = Number(row.qty)
      if (row.qty === '' || Number.isNaN(q) || q <= 0) e[`row.${row.id}`] = 'Enter a quantity above 0'
      if (!row.factor?.factor_id) e[`factor.${row.id}`] = 'Choose an emission factor for this entry'
    })
  })
  return e
}

// Change history: consecutive keystrokes in the same text field within 10s merge into one entry.
const isTyped = (key) => key.startsWith('facility.') || key.endsWith('.qty') || key === 'customSubsector'

function log(a, key, what, from, to) {
  if (String(from ?? '') === String(to ?? '')) return
  const last = a.history[0]
  const now = Date.now()
  if (isTyped(key) && last && last.key === key && now - last.at < 10000) {
    last.to = to
    last.at = now
    if (String(last.from ?? '') === String(to ?? '')) a.history.shift()
    return
  }
  a.history.unshift({ key, at: now, what, from: from ?? '', to: to ?? '' })
  a.history = a.history.slice(0, 200)
}

const FIELD_LABEL = {
  name: 'Facility name', type: 'Facility type', address: 'Address', city: 'City', state: 'State',
  country: 'Country', pincode: 'PIN / ZIP', lat: 'Latitude', lng: 'Longitude',
}

export default function AuditPage() {
  const [audit, setAudit] = useState(() => loadDraft() ?? emptyAudit())
  const [customIndustries, setCustomIndustries] = useState(loadCustomIndustries)
  const [attempted, setAttempted] = useState(false)
  const [result, setResult] = useState(null)
  const [resultFor, setResultFor] = useState('')
  const [calculating, setCalculating] = useState(false)
  const [draftMsg, setDraftMsg] = useState('')
  const [adding, setAdding] = useState(false)
  const [newProc, setNewProc] = useState('')
  const [customName, setCustomName] = useState('')
  const [addingIndustry, setAddingIndustry] = useState(false)
  const [industryName, setIndustryName] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const [geoMsg, setGeoMsg] = useState('')
  const [apiError, setApiError] = useState('')
  const draftRef = useRef(null) // { signature, report } for the factor picker and the next calculation

  const industries = useMemo(
    () => [...INDUSTRIES, ...customIndustries.map((c) => ({ ...c, icon: 'layers', custom: true, subsectors: [] }))],
    [customIndustries],
  )
  const industry = industries.find((i) => i.id === audit.industryId)
  const isCustom = !!industry?.custom
  const subsector = industry?.subsectors.find((s) => s.id === audit.subsectorId)
  const ready = isCustom ? audit.customSubsector.trim() !== '' : !!subsector
  const unusedProcesses = subsector?.processes.filter((p) => !audit.processes.some((s) => s.name === p.name)) ?? []

  const errors = useMemo(() => (attempted ? validate(audit, isCustom) : {}), [attempted, audit, isCustom])
  const errorCount = Object.keys(errors).length
  const calcKey = JSON.stringify({ ...audit, history: undefined })
  const stale = result && calcKey !== resultFor
  const country = COUNTRIES[audit.facility.country] ?? COUNTRIES.India

  const update = (fn) => setAudit((a) => fn(structuredClone(a)))

  const setFacility = (key, value) => update((a) => {
    log(a, `facility.${key}`, FIELD_LABEL[key], a.facility[key], value)
    a.facility[key] = value
    return a
  })

  const setPeriod = (patch) => update((a) => {
    const next = { ...a.period, ...patch }
    if (patch.type || patch.start) next.end = periodEnd(next.type, next.start) || next.end
    log(a, 'period', 'Reporting period', fmtPeriod(a.period), fmtPeriod(next))
    a.period = next
    return a
  })

  const setTop = (key, label, value) => update((a) => { log(a, key, label, a[key], value); a[key] = value; return a })

  const selectIndustry = (id) => update((a) => {
    if (a.industryId !== id) {
      log(a, 'industry', 'Industry', industries.find((i) => i.id === a.industryId)?.name, industries.find((i) => i.id === id)?.name)
      a.industryId = id; a.subsectorId = ''; a.customSubsector = ''; a.processes = []
    }
    return a
  })

  const selectSubsector = (id) => update((a) => {
    const sub = industry.subsectors.find((s) => s.id === id)
    log(a, 'subsector', 'Sub-sector', industry.subsectors.find((s) => s.id === a.subsectorId)?.name, sub?.name)
    a.subsectorId = id
    a.processes = (sub?.processes ?? []).map((process) => newProcess(a, process))
    return a
  })

  const addIndustry = () => {
    const name = industryName.trim()
    if (!name) return
    const id = `custom-${uid()}`
    const next = [...customIndustries, { id, name }]
    setCustomIndustries(next); saveCustomIndustries(next)
    setAddingIndustry(false); setIndustryName('')
    selectIndustry(id)
  }

  const removeIndustry = (id) => {
    const target = customIndustries.find((c) => c.id === id)
    if (!window.confirm(`Remove the "${target.name}" industry from the list?`)) return
    const next = customIndustries.filter((c) => c.id !== id)
    setCustomIndustries(next); saveCustomIndustries(next)
    if (audit.industryId === id) update((a) => { a.industryId = ''; a.processes = []; return a })
  }

  // Any change to a verified entry voids its verification.
  const touch = (a, row) => {
    if (row.verified) {
      log(a, `${row.entryId}.verify`, `${row.entryId} status`, 'Verified', 'Unverified (changed after verification)')
      row.verified = null
      row.reset = true
    }
  }

  const findRow = (a, procId, rowId) => a.processes.find((p) => p.id === procId).rows.find((r) => r.id === rowId)

  const updateRow = (procId, rowId, patch) => update((a) => {
    const row = findRow(a, procId, rowId)
    for (const [k, v] of Object.entries(patch)) {
      const show = (val) => (k === 'sourceId' ? SOURCES[val]?.name : k === 'scope' ? (val ? `Scope ${val}` : 'Suggested') : k === 'factor' ? (val?.label || 'None') : val)
      log(a, `${row.entryId}.${k}`, `${row.entryId} ${k === 'sourceId' ? 'fuel / energy' : k === 'qty' ? 'quantity' : k === 'factor' ? 'emission factor' : k}`, show(row[k]), show(v))
    }
    touch(a, row)
    Object.assign(row, patch)
    if (patch.sourceId) { row.unit = firstUnit(patch.sourceId); row.scope = null; row.factor = null }
    // Unit and scope always come from the chosen factor.
    if (patch.factor !== undefined) {
      row.unit = patch.factor ? patch.factor.activity_unit : firstUnit(row.sourceId)
      row.scope = patch.factor ? patch.factor.scope_number : null
    }
    return a
  })

  const attachEvidence = async (procId, rowId, file) => {
    if (!file) return
    const hash = await sha256(await file.arrayBuffer())
    update((a) => {
      const row = findRow(a, procId, rowId)
      log(a, `${row.entryId}.evidence`, `${row.entryId} evidence`, row.evidence?.name, file.name)
      touch(a, row)
      row.evidence = { name: file.name, size: file.size, hash }
      return a
    })
  }

  const removeEvidence = (procId, rowId) => update((a) => {
    const row = findRow(a, procId, rowId)
    log(a, `${row.entryId}.evidence`, `${row.entryId} evidence`, row.evidence?.name, '')
    touch(a, row)
    row.evidence = null
    return a
  })

  // The checksum freezes the entry + evidence at approval time. The backend will
  // store it and re-check it so a swapped invoice is detected later.
  const verifyRow = async (procId, rowId) => {
    const row = audit.processes.find((p) => p.id === procId).rows.find((r) => r.id === rowId)
    const payload = JSON.stringify({ s: row.sourceId, q: row.qty, u: row.unit, sc: effectiveScope(row), f: row.factor?.factor_id, e: row.evidence?.hash })
    const hash = await sha256(new TextEncoder().encode(payload))
    update((a) => {
      const r = findRow(a, procId, rowId)
      log(a, `${r.entryId}.verify`, `${r.entryId} status`, 'Unverified', 'Verified')
      r.verified = { at: Date.now(), by: 'Anushka Garud', hash }
      r.reset = false
      return a
    })
  }

  const addRow = (procId, sources) => update((a) => {
    const proc = a.processes.find((p) => p.id === procId)
    const unused = sources.find((id) => !proc.rows.some((r) => r.sourceId === id)) ?? sources[0]
    const row = newRow(a, unused)
    log(a, `${row.entryId}.add`, `${proc.name}`, '', `Added ${row.entryId}`)
    proc.rows.push(row)
    return a
  })

  const removeRow = (procId, rowId) => update((a) => {
    const proc = a.processes.find((p) => p.id === procId)
    const row = proc.rows.find((r) => r.id === rowId)
    log(a, `${row.entryId}.remove`, proc.name, row.entryId, 'Removed')
    proc.rows = proc.rows.filter((r) => r.id !== rowId)
    return a
  })

  const removeProcess = (procId) => update((a) => {
    const proc = a.processes.find((p) => p.id === procId)
    log(a, `proc.${procId}`, 'Process / activity', proc.name, 'Removed')
    a.processes = a.processes.filter((p) => p.id !== procId)
    return a
  })

  const confirmAddProcess = () => {
    if (newProc === '__custom') {
      if (!customName.trim()) return
      update((a) => {
        a.processes.push(newProcess(a, { name: customName.trim(), sources: ['grid_electricity'] }))
        log(a, `proc.add.${a.nextEntry}`, 'Process / activity', '', `Added ${customName.trim()}`)
        return a
      })
    } else {
      const process = subsector.processes.find((p) => p.name === newProc)
      if (!process) return
      update((a) => { a.processes.push(newProcess(a, process)); log(a, `proc.add.${a.nextEntry}`, 'Process / activity', '', `Added ${process.name}`); return a })
    }
    setAdding(false); setNewProc(''); setCustomName('')
  }

  const useMyLocation = () => {
    if (!navigator.geolocation) { setGeoMsg('Location is not available in this browser'); return }
    setGeoMsg('Locating…')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setFacility('lat', pos.coords.latitude.toFixed(5))
        setFacility('lng', pos.coords.longitude.toFixed(5))
        setGeoMsg('')
      },
      () => setGeoMsg("Couldn't get your location — enter it manually"),
    )
  }

  // Factor search needs a report whose dataset is pinned. One draft report is
  // created for the current facility/period/industry and reused until it is
  // calculated, so searching alone never creates more than one.
  const reportMeta = () => ({
    industryId: audit.industryId,
    industryName: industry?.name || '',
    subsectorName: isCustom ? audit.customSubsector.trim() : subsector?.name || '',
  })

  const getReport = async () => {
    const meta = reportMeta()
    const signature = reportSignature(audit, meta)
    if (draftRef.current?.signature === signature) return draftRef.current.report
    const report = await createDraftReport(audit, meta)
    draftRef.current = { signature, report }
    return report
  }

  const calculate = async () => {
    setAttempted(true)
    if (Object.keys(validate(audit, isCustom)).length > 0) return
    setCalculating(true)
    setApiError('')
    setResult(null)
    try {
      const report = await getReport()
      const r = await requestCalculation(audit, { report })
      setResult(r)
      setResultFor(calcKey)
      setDraftMsg('Calculation saved to the Carbon Audit backend.')
      setTimeout(() => document.getElementById('result')?.scrollIntoView({ behavior: 'smooth' }), 50)
    } catch (error) {
      setResult(null)
      setResultFor('')
      setApiError(error?.message || 'The backend could not calculate this audit.')
    } finally {
      // A report receives one calculation run, so recalculating can never double-count.
      draftRef.current = null
      setCalculating(false)
    }
  }

  const onSaveDraft = () => {
    setDraftMsg(saveDraft(audit) ? `Draft saved ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : "Couldn't save the draft in this browser")
  }

  const onReset = (next) => {
    setAudit(next); setAttempted(false); setResult(null); setResultFor(''); setDraftMsg(''); setApiError(''); draftRef.current = null
    if (next.industryId === '') clearDraft()
  }

  const generateReport = () => {
    if (!result?.reportId) {
      setApiError('No saved backend report is available. Calculate the audit successfully first.')
      return
    }
    clearDraft()
    navigate(`/reports/${result.reportId}`)
  }

  const err = (key) => errors[key] && <div className="err">{errors[key]}</div>
  const bad = (key) => (errors[key] ? 'bad' : '')

  const allRows = audit.processes.flatMap((p) => p.rows)
  const verifiedCount = allRows.filter((r) => r.verified).length

  return (
    <>
      <div className="top">
        <span>Carbon audit <span className="sep">/</span> <b>New audit</b></span>
        <button className="btn ghost sm top-right" onClick={() => setShowHistory(true)}>
          <Icon name="history" size={16} />Change history{audit.history.length > 0 && <span className="count">{audit.history.length}</span>}
        </button>
      </div>
      <main className="main">
        <div className="page-head">
          <div>
            <h1>New carbon audit</h1>
            <p className="sub">Enter facility details, pick the industry, then add the fuel and energy used in each process / activity.</p>
          </div>
          <div className="head-actions">
            <button className="btn ghost" onClick={() => onReset(sampleAudit())}>Fill sample data</button>
            <button className="btn ghost" onClick={() => onReset(emptyAudit())}>Clear form</button>
          </div>
        </div>

        {/* 1. Facility */}
        <section className="card">
          <div className="ch">
            <h3><span className="num">1</span>Facility details</h3>
            <p>The address decides which emission factors apply</p>
          </div>
          <div className="cb">
            <div className="r4">
              <div className="span2">
                <label htmlFor="f-name">Facility / organisation name <span className="req">*</span></label>
                <input id="f-name" className={bad('facility.name')} value={audit.facility.name}
                  placeholder="Sahyadri Steels Pvt. Ltd." onChange={(e) => setFacility('name', e.target.value)} />
                {err('facility.name')}
              </div>
              <div>
                <label htmlFor="f-type">Facility type</label>
                <select id="f-type" value={audit.facility.type} onChange={(e) => setFacility('type', e.target.value)}>
                  {FACILITY_TYPES.map((t) => <option key={t}>{t}</option>)}
                </select>
              </div>
              <div />
              <div className="span2">
                <label htmlFor="f-addr">Street address <span className="req">*</span></label>
                <input id="f-addr" className={bad('facility.address')} value={audit.facility.address}
                  placeholder="Plot 14, MIDC Bhosari" onChange={(e) => setFacility('address', e.target.value)} />
                {err('facility.address')}
              </div>
              <div>
                <label htmlFor="f-city">City <span className="req">*</span></label>
                <input id="f-city" className={bad('facility.city')} value={audit.facility.city}
                  placeholder="Pune" onChange={(e) => setFacility('city', e.target.value)} />
                {err('facility.city')}
              </div>
              <div>
                <label htmlFor="f-state">State / region</label>
                <input id="f-state" value={audit.facility.state} placeholder="Maharashtra" onChange={(e) => setFacility('state', e.target.value)} />
              </div>
              <div>
                <label htmlFor="f-country">Country <span className="req">*</span></label>
                <select id="f-country" value={audit.facility.country} onChange={(e) => setFacility('country', e.target.value)}>
                  {Object.keys(COUNTRIES).map((c) => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="f-pin">PIN / ZIP code</label>
                <input id="f-pin" value={audit.facility.pincode} placeholder="411026" onChange={(e) => setFacility('pincode', e.target.value)} />
              </div>
              <div>
                <label htmlFor="f-lat">Latitude</label>
                <input id="f-lat" value={audit.facility.lat} placeholder="18.6298" inputMode="decimal" onChange={(e) => setFacility('lat', e.target.value)} />
              </div>
              <div>
                <label htmlFor="f-lng">Longitude</label>
                <div className="with-btn">
                  <input id="f-lng" value={audit.facility.lng} placeholder="73.8470" inputMode="decimal" onChange={(e) => setFacility('lng', e.target.value)} />
                  <button className="icon-btn neutral" title="Use my current location" aria-label="Use my current location" onClick={useMyLocation}><Icon name="pin" size={16} /></button>
                </div>
                {geoMsg && <div className="hint">{geoMsg}</div>}
              </div>
            </div>
          </div>
        </section>

        {/* 2. Reporting period & standards */}
        <section className="card">
          <div className="ch"><h3><span className="num">2</span>Reporting period and standards</h3></div>
          <div className="cb">
            <div className="r4">
              <div>
                <label htmlFor="p-type">Period type</label>
                <select id="p-type" value={audit.period.type} onChange={(e) => setPeriod({ type: e.target.value })}>
                  {PERIOD_TYPES.map((t) => <option key={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="p-start">Reporting start <span className="req">*</span></label>
                <input id="p-start" type="date" className={bad('period.start')} value={audit.period.start} onChange={(e) => setPeriod({ start: e.target.value })} />
                {err('period.start')}
              </div>
              <div>
                <label htmlFor="p-end">Reporting end <span className="req">*</span></label>
                <input id="p-end" type="date" className={bad('period.end')} value={audit.period.end}
                  onChange={(e) => update((a) => { log(a, 'period', 'Reporting period', fmtPeriod(a.period), fmtPeriod({ ...a.period, end: e.target.value, type: 'Custom' })); a.period = { ...a.period, end: e.target.value, type: 'Custom' }; return a })} />
                {err('period.end')}
              </div>
              <div>
                <label htmlFor="p-fw">Reporting framework</label>
                <select id="p-fw" value={audit.framework} onChange={(e) => setTop('framework', 'Reporting framework', e.target.value)}>
                  {FRAMEWORKS.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="p-ef">Emission factors (Scope 1 &amp; 3)</label>
                <select id="p-ef" value={audit.factorSource} onChange={(e) => setTop('factorSource', 'Emission factor database', e.target.value)}>
                  {FACTOR_SOURCES.map((s) => <option key={s}>{s}{s === 'DEFRA 2026' ? ' (available)' : ''}</option>)}
                </select>
              </div>
              <div>
                <label>Emission factors (Scope 2)</label>
                <div className="readonly">{country.gridSource}<span className="hint"> · from country</span></div>
              </div>
              <div className="span2 check-cell">
                <label className="check">
                  <input type="checkbox" checked={false} disabled readOnly />
                  IPCC fallback is not enabled in this version; unsupported factors are not substituted.
                </label>
              </div>
              <div className="span2 note">
                Each activity entry is calculated with the emission factor you choose from the UK DEFRA 2026 dataset pinned to the report. Industry and process names are labels only and can be anything. Nothing is matched automatically, so check that the factor suits the activity.
              </div>
            </div>
          </div>
        </section>

        {/* 3. Industry */}
        <section className="card">
          <div className="ch"><h3><span className="num">3</span>Industry</h3><p>Choose one, or add your own</p></div>
          <div className="cb">
            <div className="ind" role="radiogroup" aria-label="Industry">
              {industries.map((ind) => (
                <div className="it-wrap" key={ind.id}>
                  <button role="radio" aria-checked={audit.industryId === ind.id}
                    className={`it ${audit.industryId === ind.id ? 'on' : ''}`} onClick={() => selectIndustry(ind.id)}>
                    <Icon name={ind.icon} size={22} />{ind.name}
                  </button>
                  {ind.custom && (
                    <button className="it-del" aria-label={`Remove ${ind.name}`} title="Remove industry" onClick={() => removeIndustry(ind.id)}>
                      <Icon name="x" size={12} />
                    </button>
                  )}
                </div>
              ))}
              {!addingIndustry && (
                <button className="it add-it" onClick={() => setAddingIndustry(true)}><Icon name="plus" size={22} />Add industry</button>
              )}
            </div>
            {addingIndustry && (
              <div className="addform">
                <input aria-label="New industry name" placeholder="Cement & Building Materials" value={industryName} autoFocus
                  onChange={(e) => setIndustryName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addIndustry()} />
                <button className="btn p sm" onClick={addIndustry}>Add industry</button>
                <button className="btn ghost sm" onClick={() => { setAddingIndustry(false); setIndustryName('') }}>Cancel</button>
              </div>
            )}
            {err('industry')}
            {industry && (
              <div className="r3 mt">
                <div>
                  <label htmlFor="sub">Sub-sector / facility type <span className="req">*</span></label>
                  {isCustom ? (
                    <input id="sub" className={bad('subsector')} value={audit.customSubsector} placeholder="Clinker production"
                      onChange={(e) => setTop('customSubsector', 'Sub-sector', e.target.value)} />
                  ) : (
                    <select id="sub" className={bad('subsector')} value={audit.subsectorId} onChange={(e) => selectSubsector(e.target.value)}>
                      <option value="" disabled>Select a sub-sector</option>
                      {industry.subsectors.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  )}
                  {err('subsector')}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* 4. Processes / activities */}
        <section className="card">
          <div className="ch">
            <h3><span className="num">4</span>Processes / activities and fuel used</h3>
            <p>{ready && audit.processes.length > 0 ? `${verifiedCount} of ${allRows.length} entries verified` : 'Loaded from the sub-sector template'}</p>
          </div>
          <div className="cb">
            {!industry && <div className="empty">Choose an industry and sub-sector to load its processes.</div>}
            {industry && !isCustom && subsector && (
              <div className="note">Template loaded for <b>{subsector.name}</b>. Remove what doesn't apply to you and add what's missing.</div>
            )}
            {isCustom && ready && audit.processes.length === 0 && (
              <div className="note">Custom industry — add each process / activity your facility runs.</div>
            )}

            {audit.processes.map((proc, i) => {
              const sources = subsector?.processes.find((p) => p.name === proc.name)?.sources ?? ALL_SOURCE_IDS
              return (
                <div className="step" key={proc.id}>
                  <div className="sh">
                    <b><span className="sn">Process {i + 1}</span>{proc.name}</b>
                    <div className="sh-right">
                      <span>{proc.rows.length} {proc.rows.length === 1 ? 'entry' : 'entries'}</span>
                      <button className="icon-btn" aria-label={`Remove ${proc.name}`} onClick={() => removeProcess(proc.id)}><Icon name="trash" size={16} /></button>
                    </div>
                  </div>
                  {proc.rows.length > 0 && (
                    <div className="srow h"><span>Fuel / energy</span><span>Quantity consumed</span><span>Unit</span><span>Scope</span><span /></div>
                  )}
                  {proc.rows.map((row) => {
                    return (
                      <div className="entry" key={row.id}>
                        <div className="srow">
                          <select aria-label="Fuel / energy" value={row.sourceId}
                            onChange={(e) => updateRow(proc.id, row.id, { sourceId: e.target.value })}>
                            {sources.map((id) => <option key={id} value={id}>{SOURCES[id].name}</option>)}
                          </select>
                          <div>
                            <input aria-label="Quantity consumed" type="number" min="0" step="any" inputMode="decimal"
                              className={bad(`row.${row.id}`)} value={row.qty} placeholder="0"
                              onChange={(e) => updateRow(proc.id, row.id, { qty: e.target.value })} />
                            {err(`row.${row.id}`)}
                          </div>
                          <div className="readonly">{row.factor ? row.factor.activity_unit : <span className="hint">Set by factor</span>}</div>
                          <div>{row.factor ? <ScopeTag scope={row.factor.scope_number} /> : <span className="hint">Set by factor</span>}</div>
                          <button className="icon-btn" aria-label={`Remove ${row.entryId}`} onClick={() => removeRow(proc.id, row.id)}><Icon name="x" size={16} /></button>
                        </div>
                        <FactorPicker key={row.sourceId} sourceId={row.sourceId} selected={row.factor} error={errors[`factor.${row.id}`]}
                          getReport={getReport}
                          onChoose={(factor) => updateRow(proc.id, row.id, { factor })}
                          onClear={() => updateRow(proc.id, row.id, { factor: null })} />
                        <div className="rmeta">
                          <span className="eid">{row.entryId}</span>
                          {row.evidence ? (
                            <span className="file" title={`SHA-256 ${row.evidence.hash}`}>
                              <Icon name="clip" size={14} />{row.evidence.name}
                              <span className="hash">#{row.evidence.hash.slice(0, 8)}</span>
                              <button className="icon-btn tiny" aria-label="Remove evidence" onClick={() => removeEvidence(proc.id, row.id)}><Icon name="x" size={12} /></button>
                            </span>
                          ) : (
                            <label className="attach">
                              <input type="file" accept="image/*,.pdf" hidden onChange={(e) => { attachEvidence(proc.id, row.id, e.target.files[0]); e.target.value = '' }} />
                              <Icon name="clip" size={14} />Attach invoice / evidence
                            </label>
                          )}
                          <span className="rmeta-right">
                            {row.verified ? (
                              <span className="status ok" title={`Checksum ${row.verified.hash}`}>
                                <Icon name="check" size={13} />Verified by {row.verified.by.split(' ')[0]} · {new Date(row.verified.at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                              </span>
                            ) : (
                              <>
                                <span className={`status ${row.reset ? 'warn' : ''}`}>{row.reset ? 'Changed after verification' : 'Unverified'}</span>
                                <button className="btn sm xs" disabled={!row.evidence || !row.qty}
                                  title={!row.evidence ? 'Attach evidence before verifying' : ''} onClick={() => verifyRow(proc.id, row.id)}>Mark verified</button>
                              </>
                            )}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                  {err(`proc.${proc.id}`) && <div className="pad-x">{err(`proc.${proc.id}`)}</div>}
                  <button className="add" onClick={() => addRow(proc.id, sources)}><Icon name="plus" size={14} />Add fuel / energy</button>
                </div>
              )
            })}

            {err('processes')}

            {ready && !adding && (
              <button className="addstep" onClick={() => { setAdding(true); setNewProc(unusedProcesses[0]?.name ?? '__custom') }}>
                <Icon name="plus" size={16} />Add process / activity
              </button>
            )}

            {ready && adding && (
              <div className="addform">
                <select aria-label="Process / activity" value={newProc} onChange={(e) => setNewProc(e.target.value)}>
                  {unusedProcesses.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
                  <option value="__custom">Custom process / activity…</option>
                </select>
                {newProc === '__custom' && (
                  <input aria-label="Custom process name" placeholder="Rolling mill" value={customName}
                    onChange={(e) => setCustomName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && confirmAddProcess()} autoFocus />
                )}
                <button className="btn p sm" onClick={confirmAddProcess}>Add</button>
                <button className="btn ghost sm" onClick={() => setAdding(false)}>Cancel</button>
              </div>
            )}
          </div>
        </section>

        {/* Calculate bar */}
        {apiError && <div className="calc-err" role="alert"><Icon name="alert" size={16} />{apiError}</div>}
        <div className="calc">
          <div>
            {attempted && errorCount > 0 ? (
              <div className="calc-err"><Icon name="alert" size={16} />Fix {errorCount} {errorCount === 1 ? 'field' : 'fields'} highlighted above</div>
            ) : (
              <div className="calc-title">Ready to calculate</div>
            )}
            <div className="calc-sub">
              {draftMsg || `Factor source: ${audit.factorSource} · Current supported geography: United Kingdom`}
            </div>
          </div>
          <div className="calc-actions">
            <button className="btn" onClick={onSaveDraft}>Save draft</button>
            <button className="btn p" onClick={calculate} disabled={calculating}>{calculating ? 'Calculating…' : 'Calculate emissions'}</button>
          </div>
        </div>

        {/* 5. Result */}
        {result && (
          <section className="card" id="result">
            <div className="ch">
              <h3><span className="num">5</span>Result</h3>
              {!stale && <button className="btn p sm" onClick={generateReport}>Generate carbon report →</button>}
            </div>
            {stale && (
              <div className="stale">Inputs changed since the last calculation. <button className="link" onClick={calculate}>Recalculate</button></div>
            )}
            <ResultSummary result={result} />
          </section>
        )}
      </main>

      {showHistory && (
        <>
          <div className="scrim" onClick={() => setShowHistory(false)} />
          <aside className="drawer" aria-label="Change history">
            <div className="drawer-head">
              <h3>Change history</h3>
              <button className="icon-btn neutral" aria-label="Close" onClick={() => setShowHistory(false)}><Icon name="x" size={16} /></button>
            </div>
            <p className="drawer-sub">Every edit with its previous and new value. Saved with the draft.</p>
            {audit.history.length === 0 ? (
              <div className="empty sm">No changes yet.</div>
            ) : (
              <ol className="hist">
                {audit.history.map((h, i) => (
                  <li key={i}>
                    <div className="hist-top"><b>{h.what}</b><span>{new Date(h.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></div>
                    <div className="hist-diff">
                      {h.from !== '' && <span className="old">{String(h.from)}</span>}
                      {h.from !== '' && <span className="arrow">→</span>}
                      <span className="new">{h.to === '' ? '(empty)' : String(h.to)}</span>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </aside>
        </>
      )}
    </>
  )
}
