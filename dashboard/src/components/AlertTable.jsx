/**
 * AlertTable.jsx
 * Clean table of all alerts, newest first.
 * Government/municipal control room aesthetic.
 */

const EVENT_LABELS = {
  pothole: { label: 'Pothole', color: '#c53030', bg: '#fff5f5' },
  vehicle_congestion: { label: 'Congestion', color: '#c05621', bg: '#fffaf0' },
  traffic_density: { label: 'Traffic', color: '#2c5282', bg: '#ebf8ff' },
}

const STATUS_CONFIG = ['New', 'Reviewed', 'Resolved']

function formatTimestamp(ts) {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    return d.toLocaleString('en-IN', {
      day: '2-digit', month: 'short',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ts
  }
}

function formatGPS(gps) {
  if (!gps) return '—'
  return `${gps.lat.toFixed(4)}, ${gps.lng.toFixed(4)}`
}

export default function AlertTable({ alerts, selectedAlert, onSelect, onGenerateReport }) {
  if (!alerts || alerts.length === 0) {
    return (
      <div style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <TableHeader count={0} />
        <div style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--color-text-muted)',
          fontSize: 13,
        }}>
          No alerts yet — run detection scripts to generate data
        </div>
      </div>
    )
  }

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <TableHeader count={alerts.length} />

      {/* Scrollable table body */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 12,
        }}>
          <thead>
            <tr style={{
              background: '#f7fafc',
              borderBottom: '1px solid var(--color-border)',
              position: 'sticky',
              top: 0,
              zIndex: 1,
            }}>
              {['Time', 'Event', 'Location (Simulated GPS)', 'Confidence', 'Bus ID', 'Status', 'Actions'].map(h => (
                <th key={h} style={{
                  padding: '8px 12px',
                  textAlign: 'left',
                  fontWeight: 600,
                  color: 'var(--color-text-secondary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  fontSize: 10,
                  whiteSpace: 'nowrap',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {alerts.map((alert, idx) => {
              const evCfg = EVENT_LABELS[alert.event_type] || { label: alert.event_type, color: '#4a5568', bg: '#f7fafc' }
              const isSelected = selectedAlert?.id === alert.id
              const confPct = ((alert.confidence || 0) * 100).toFixed(0)

              return (
                <tr
                  key={alert.id || idx}
                  onClick={() => onSelect(alert)}
                  style={{
                    borderBottom: '1px solid var(--color-border-light)',
                    cursor: 'pointer',
                    background: isSelected ? '#ebf8ff' : (idx % 2 === 0 ? '#fff' : '#f8f9fa'),
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => {
                    if (!isSelected) e.currentTarget.style.background = '#f0f4f8'
                  }}
                  onMouseLeave={e => {
                    if (!isSelected) e.currentTarget.style.background = idx % 2 === 0 ? '#fff' : '#f8f9fa'
                  }}
                >
                  <td style={{ padding: '8px 12px', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                    {formatTimestamp(alert.timestamp)}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '2px 7px',
                      borderRadius: 3,
                      fontSize: 11,
                      fontWeight: 600,
                      background: evCfg.bg,
                      color: evCfg.color,
                      border: `1px solid ${evCfg.color}30`,
                    }}>
                      {evCfg.label}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}>
                    {formatGPS(alert.gps)}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{
                      color: confPct >= 80 ? '#276749' : confPct >= 60 ? '#975a16' : '#c53030',
                      fontWeight: 600,
                    }}>
                      {confPct}%
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                    {alert.bus_id || '—'}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '1px 6px',
                      borderRadius: 2,
                      fontSize: 10,
                      fontWeight: 600,
                      background: '#f0fff4',
                      color: '#276749',
                      border: '1px solid #c6f6d5',
                      textTransform: 'uppercase',
                    }}>
                      New
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {alert.event_type === 'pothole' && (
                      <button
                        id={`report-btn-${alert.id?.slice(0,8) || idx}`}
                        onClick={(e) => { e.stopPropagation(); onGenerateReport(alert) }}
                        style={{
                          fontSize: 10,
                          padding: '3px 8px',
                          border: '1px solid #2c5282',
                          borderRadius: 3,
                          background: '#fff',
                          color: '#2c5282',
                          cursor: 'pointer',
                          fontWeight: 600,
                          fontFamily: 'inherit',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Generate Report
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TableHeader({ count }) {
  return (
    <div style={{
      padding: '10px 16px',
      borderBottom: '1px solid var(--color-border)',
      background: '#fff',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      flexShrink: 0,
    }}>
      <h2 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: 'var(--color-text-primary)' }}>
        Recent Alerts
      </h2>
      <span style={{
        fontSize: 11,
        color: 'var(--color-text-muted)',
        background: '#f7fafc',
        border: '1px solid var(--color-border)',
        borderRadius: 10,
        padding: '1px 8px',
      }}>
        {count} total
      </span>
    </div>
  )
}
