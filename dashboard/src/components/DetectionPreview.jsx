/**
 * DetectionPreview.jsx
 * Sidebar panel showing selected alert details and evidence image.
 */

function formatTimestamp(ts) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('en-IN')
  } catch {
    return ts
  }
}

function Row({ label, value }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      paddingBottom: 10,
      borderBottom: '1px solid var(--color-border-light)',
      marginBottom: 10,
    }}>
      <span style={{
        fontSize: 10,
        fontWeight: 600,
        color: 'var(--color-text-muted)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        marginBottom: 2,
      }}>
        {label}
      </span>
      <span style={{
        fontSize: 13,
        color: 'var(--color-text-primary)',
        fontWeight: 500,
        wordBreak: 'break-all',
      }}>
        {value || '—'}
      </span>
    </div>
  )
}

export default function DetectionPreview({ alert }) {
  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: '#fff',
    }}>
      {/* Panel header */}
      <div style={{
        padding: '10px 16px',
        borderBottom: '1px solid var(--color-border)',
        background: '#fff',
        flexShrink: 0,
      }}>
        <h2 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: 'var(--color-text-primary)' }}>
          Detection Preview
        </h2>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {!alert ? (
          <div style={{
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--color-text-muted)',
            fontSize: 12,
            textAlign: 'center',
            gap: 8,
          }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.4 }}>
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M3 9h18M9 21V9" />
            </svg>
            No detection selected
            <span style={{ fontSize: 11 }}>Click a marker or table row</span>
          </div>
        ) : (
          <>
            {/* Event type badge */}
            <div style={{
              display: 'inline-block',
              padding: '3px 10px',
              borderRadius: 3,
              fontSize: 11,
              fontWeight: 700,
              background: alert.event_type === 'pothole' ? '#fff5f5' : '#ebf8ff',
              color: alert.event_type === 'pothole' ? '#c53030' : '#2c5282',
              border: `1px solid ${alert.event_type === 'pothole' ? '#fc818140' : '#90cdf440'}`,
              marginBottom: 14,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}>
              {alert.event_type?.replace('_', ' ')}
            </div>

            <Row label="Event ID" value={alert.id?.slice(0, 16) + '...'} />
            <Row
              label="Confidence"
              value={`${((alert.confidence || 0) * 100).toFixed(1)}%`}
            />
            <Row
              label="Timestamp"
              value={formatTimestamp(alert.timestamp)}
            />
            <Row
              label="GPS (Simulated)"
              value={alert.gps
                ? `${alert.gps.lat.toFixed(5)}, ${alert.gps.lng.toFixed(5)}`
                : '—'
              }
            />
            <Row label="Bus ID" value={alert.bus_id} />

            {/* Evidence image */}
            {alert.image_path && (
              <div style={{ marginTop: 4 }}>
                <div style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: 'var(--color-text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: 8,
                }}>
                  Evidence Image
                </div>
                <div style={{
                  border: '1px solid var(--color-border)',
                  borderRadius: 3,
                  overflow: 'hidden',
                  background: '#f8f9fa',
                }}>
                  <img
                    src={alert.image_path}
                    alt="Pothole evidence"
                    style={{
                      width: '100%',
                      display: 'block',
                      objectFit: 'cover',
                    }}
                    onError={(e) => {
                      e.target.parentElement.innerHTML = '<div style="padding:16px;text-align:center;color:#718096;font-size:11px;">Image not available</div>'
                    }}
                  />
                </div>
                <p style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 4 }}>
                  Cropped from dashcam frame
                </p>
              </div>
            )}

            {/* Vehicle counts for congestion alerts */}
            {alert.classes && (
              <div style={{ marginTop: 8 }}>
                <div style={{
                  fontSize: 10, fontWeight: 600, color: 'var(--color-text-muted)',
                  textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6,
                }}>Vehicle Breakdown</div>
                {Object.entries(alert.classes).map(([cls, cnt]) => cnt > 0 && (
                  <div key={cls} style={{
                    display: 'flex', justifyContent: 'space-between',
                    fontSize: 12, padding: '3px 0',
                    borderBottom: '1px solid var(--color-border-light)',
                  }}>
                    <span style={{ color: 'var(--color-text-secondary)', textTransform: 'capitalize' }}>{cls}</span>
                    <span style={{ fontWeight: 600 }}>{cnt}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
