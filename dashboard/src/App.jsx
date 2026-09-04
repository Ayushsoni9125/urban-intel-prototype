import { useState, useEffect, useCallback } from 'react'
import Header from './components/Header'
import StatsBar from './components/StatsBar'
import MapView from './components/MapView'
import AlertTable from './components/AlertTable'
import DetectionPreview from './components/DetectionPreview'
import IncidentReport from './components/IncidentReport'

const API_BASE = ''  // Vite proxy forwards /api → localhost:8000

const POLL_INTERVAL_MS = 5000  // poll every 5 seconds

export default function App() {
  const [alerts, setAlerts] = useState([])
  const [traffic, setTraffic] = useState([])
  const [stats, setStats] = useState(null)
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [showReport, setShowReport] = useState(false)
  const [reportAlert, setReportAlert] = useState(null)
  const [apiStatus, setApiStatus] = useState('connecting') // 'active' | 'error' | 'connecting'
  const [lastUpdated, setLastUpdated] = useState(null)

  // --------------------------------------------------
  // Fetch all data from FastAPI
  // --------------------------------------------------
  const fetchData = useCallback(async () => {
    try {
      const [alertsRes, trafficRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/alerts`),
        fetch(`${API_BASE}/api/traffic`),
        fetch(`${API_BASE}/api/stats`),
      ])

      if (!alertsRes.ok || !trafficRes.ok || !statsRes.ok) {
        throw new Error('API response not OK')
      }

      const [alertsData, trafficData, statsData] = await Promise.all([
        alertsRes.json(),
        trafficRes.json(),
        statsRes.json(),
      ])

      setAlerts(alertsData)
      setTraffic(trafficData)
      setStats(statsData)
      setApiStatus('active')
      setLastUpdated(new Date())
    } catch (err) {
      console.error('API fetch failed:', err)
      setApiStatus('error')
    }
  }, [])

  // --------------------------------------------------
  // Initial fetch + polling
  // --------------------------------------------------
  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchData])

  // --------------------------------------------------
  // Handlers
  // --------------------------------------------------
  const handleAlertSelect = (alert) => {
    setSelectedAlert(alert)
    setShowReport(false)
  }

  const handleGenerateReport = (alert) => {
    setReportAlert(alert)
    setShowReport(true)
  }

  const handleCloseReport = () => {
    setShowReport(false)
    setReportAlert(null)
  }

  // Separate pothole alerts for map markers
  const potholeAlerts = alerts.filter(a => a.event_type === 'pothole')

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--color-surface)' }}>
      {/* Header */}
      <Header apiStatus={apiStatus} lastUpdated={lastUpdated} />

      {/* Stats Bar */}
      <StatsBar stats={stats} alertCount={alerts.length} potholeCount={potholeAlerts.length} />

      {/* Main content */}
      <main className="flex-1 flex flex-col gap-0">

        {/* Split row: Video + Map */}
        <section className="flex flex-col lg:flex-row border-b" style={{ borderColor: 'var(--color-border)', height: '480px' }}>
          
          {/* Live Video Feed */}
          <div className="w-full lg:w-1/2 border-r flex flex-col" style={{ borderColor: 'var(--color-border)', backgroundColor: '#000' }}>
             <div style={{ padding: '8px 16px', background: '#fff', borderBottom: '1px solid #d1d5db', flexShrink: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
               <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                 <span style={{ fontSize: 11, fontWeight: 700, color: '#718096', letterSpacing: '0.05em' }}>LIVE DASHCAM FEED: BUS-017</span>
                 <span style={{ fontSize: 11, color: '#dc2626', fontWeight: 600 }} className="animate-pulse">● LIVE</span>
               </div>
               <div style={{ display: 'flex', gap: '8px' }}>
                 <button 
                    onClick={() => fetch(`${API_BASE}/api/start`, { method: 'POST' })}
                    style={{ fontSize: 10, fontWeight: 600, padding: '4px 8px', background: '#10b981', color: 'white', borderRadius: 3 }}
                 >▶ START AI</button>
                 <button 
                    onClick={() => fetch(`${API_BASE}/api/reset`, { method: 'POST' })}
                    style={{ fontSize: 10, fontWeight: 600, padding: '4px 8px', background: '#ef4444', color: 'white', borderRadius: 3 }}
                 >↺ RESET</button>
               </div>
             </div>
             <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
               <img 
                  src={`${API_BASE}/api/video_feed`} 
                  alt="Live Dashcam Feed"
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
               />
               <div style={{ position: 'absolute', bottom: 10, left: 10, color: 'white', background: 'rgba(0,0,0,0.5)', padding: '2px 6px', fontSize: 10, borderRadius: 3 }}>
                 AI Processed Feed
               </div>
             </div>
          </div>

          {/* Map View */}
          <div className="w-full lg:w-1/2 h-full">
            <MapView
              potholeAlerts={potholeAlerts}
              trafficData={traffic}
              onMarkerClick={handleAlertSelect}
            />
          </div>
        </section>

        {/* Bottom row — alerts table + detection preview */}
        <section className="flex flex-col lg:flex-row" style={{ minHeight: '340px' }}>
          {/* Alert Table */}
          <div className="flex-1 border-r" style={{ borderColor: 'var(--color-border)' }}>
            <AlertTable
              alerts={alerts}
              selectedAlert={selectedAlert}
              onSelect={handleAlertSelect}
              onGenerateReport={handleGenerateReport}
            />
          </div>

          {/* Detection Preview */}
          <div className="w-full lg:w-80 xl:w-96 border-t lg:border-t-0" style={{ borderColor: 'var(--color-border)' }}>
            <DetectionPreview alert={selectedAlert} />
          </div>
        </section>
      </main>

      {/* Incident Report Modal */}
      {showReport && reportAlert && (
        <IncidentReport alert={reportAlert} onClose={handleCloseReport} />
      )}
    </div>
  )
}
