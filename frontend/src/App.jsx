import { useEffect, useState } from 'react'
import Icon from './components/Icon.jsx'
import AuditPage from './pages/AuditPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import ReportView from './pages/ReportView.jsx'

// Minimal hash routing: #/dashboard, #/audit, #/reports, #/reports/RPT-2026-001
function parseHash() {
  const parts = window.location.hash.replace(/^#\/?/, '').split('/')
  if (parts[0] === 'reports' && parts[1]) return { page: 'report', id: decodeURIComponent(parts[1]) }
  if (parts[0] === 'reports') return { page: 'reports' }
  if (parts[0] === 'audit') return { page: 'audit' }
  return { page: 'dashboard' }
}

export function navigate(path) {
  window.location.hash = path
}

export default function App() {
  const [route, setRoute] = useState(parseHash)

  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const section = route.page === 'report' ? 'reports' : route.page

  return (
    <div className="app">
      <aside className="side">
        <div className="logo">
          <span className="mk"><Icon name="leaf" size={16} /></span>Carbon Audit
        </div>
        <nav>
          <a href="#/dashboard" className={`nav ${section === 'dashboard' ? 'on' : ''}`}><Icon name="grid" />Dashboard</a>
          <a href="#/audit" className={`nav ${section === 'audit' ? 'on' : ''}`}><Icon name="calc" />Carbon audit</a>
          <a href="#/reports" className={`nav ${section === 'reports' ? 'on' : ''}`}><Icon name="file" />Reports</a>
        </nav>
        <div className="user">
          <div className="av">AG</div>
          <div>
            <div className="user-name">Anushka Garud</div>
            <div className="user-org">Omnevu</div>
          </div>
        </div>
      </aside>

      <div className="content">
        {route.page === 'dashboard' && <DashboardPage />}
        {route.page === 'audit' && <AuditPage />}
        {route.page === 'reports' && <ReportsPage />}
        {route.page === 'report' && <ReportView id={route.id} />}
      </div>
    </div>
  )
}
