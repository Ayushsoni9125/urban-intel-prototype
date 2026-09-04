/**
 * IncidentReport.jsx
 * Printable official incident report modal.
 * Triggered when user clicks "Generate Report" on a pothole alert.
 *
 * Uses window.print() — print CSS hides everything except the report.
 */

function formatTimestamp(ts) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('en-IN', {
      year: 'numeric', month: 'long', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch {
    return ts
  }
}

export default function IncidentReport({ alert, onClose }) {
  if (!alert) return null

  const confPct = ((alert.confidence || 0) * 100).toFixed(1)
  const reportDate = new Date().toLocaleDateString('en-IN', {
    year: 'numeric', month: 'long', day: '2-digit',
  })

  // Short incident ID from alert UUID
  const incidentId = `INC-${alert.id?.slice(0, 8).toUpperCase() || 'UNKNOWN'}`

  const handlePrint = () => window.print()

  return (
    <>
      {/* Backdrop */}
      <div
        className="no-print"
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.5)',
          zIndex: 1000,
        }}
      />

      {/* Modal wrapper */}
      <div
        className="no-print"
        style={{
          position: 'fixed',
          inset: '40px',
          maxWidth: 680,
          margin: '0 auto',
          zIndex: 1001,
          display: 'flex',
          flexDirection: 'column',
          background: '#fff',
          borderRadius: 4,
          boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
          overflow: 'hidden',
        }}
      >
        {/* Modal toolbar */}
        <div style={{
          padding: '10px 16px',
          background: '#1a202c',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <span style={{ color: '#fff', fontSize: 13, fontWeight: 600 }}>
            Incident Report — {incidentId}
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              id="print-report-btn"
              onClick={handlePrint}
              style={{
                padding: '5px 14px',
                background: '#2c5282',
                color: '#fff',
                border: 'none',
                borderRadius: 3,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Print / Save as PDF
            </button>
            <button
              id="close-report-btn"
              onClick={onClose}
              style={{
                padding: '5px 12px',
                background: 'transparent',
                color: '#a0aec0',
                border: '1px solid #4a5568',
                borderRadius: 3,
                fontSize: 12,
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Close
            </button>
          </div>
        </div>

        {/* Scrollable report body */}
        <div style={{ flex: 1, overflow: 'auto', padding: '0' }}>
          <Report
            alert={alert}
            confPct={confPct}
            reportDate={reportDate}
            incidentId={incidentId}
          />
        </div>
      </div>

      {/* Printable version (always in DOM, shown only on print) */}
      <div id="incident-report" style={{ display: 'none' }}>
        <Report
          alert={alert}
          confPct={confPct}
          reportDate={reportDate}
          incidentId={incidentId}
        />
      </div>
    </>
  )
}

function Report({ alert, confPct, reportDate, incidentId }) {
  const sectionHead = {
    fontSize: 10,
    fontWeight: 700,
    color: '#4a5568',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    borderBottom: '1px solid #e2e8f0',
    paddingBottom: 6,
    marginBottom: 12,
    marginTop: 20,
  }

  const fieldRow = {
    display: 'grid',
    gridTemplateColumns: '160px 1fr',
    gap: '4px 16px',
    marginBottom: 10,
    fontSize: 13,
    alignItems: 'start',
  }

  const fieldLabel = {
    fontWeight: 600,
    color: '#4a5568',
  }

  const fieldValue = {
    color: '#1a202c',
  }

  return (
    <div style={{ padding: '32px 40px', fontFamily: 'Inter, Segoe UI, sans-serif', maxWidth: 640, margin: '0 auto' }}>

      {/* Official header */}
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        borderBottom: '3px solid #1a202c',
        paddingBottom: 16,
        marginBottom: 4,
      }}>
        <div>
          <div style={{ fontSize: 19, fontWeight: 700, color: '#1a202c', letterSpacing: '-0.02em' }}>
            Urban Road Intelligence
          </div>
          <div style={{ fontSize: 12, color: '#4a5568', marginTop: 3 }}>
            Public Works Department — Road Monitoring Division
          </div>
          <div style={{ fontSize: 11, color: '#718096', marginTop: 2 }}>
            AI-Assisted Road Defect Detection System | SIH 2026 Prototype
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{
            fontSize: 11, fontWeight: 700,
            background: '#1a202c', color: '#fff',
            padding: '4px 10px', borderRadius: 3,
            letterSpacing: '0.06em',
          }}>
            INCIDENT REPORT
          </div>
          <div style={{ fontSize: 11, color: '#718096', marginTop: 6 }}>
            {reportDate}
          </div>
        </div>
      </div>

      {/* Incident ID highlight */}
      <div style={{
        background: '#f7fafc',
        border: '1px solid #e2e8f0',
        borderRadius: 3,
        padding: '10px 14px',
        marginTop: 16,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ fontSize: 12, color: '#4a5568', fontWeight: 600 }}>INCIDENT ID:</span>
        <span style={{ fontSize: 16, fontWeight: 700, color: '#1a202c', letterSpacing: '0.05em' }}>
          {incidentId}
        </span>
      </div>

      {/* Incident details */}
      <div style={sectionHead}>1. Incident Details</div>
      <div style={fieldRow}>
        <span style={fieldLabel}>Event Type</span>
        <span style={{ ...fieldValue, fontWeight: 700, color: '#c53030', textTransform: 'uppercase' }}>
          {alert.event_type?.replace('_', ' ')}
        </span>
      </div>
      <div style={fieldRow}>
        <span style={fieldLabel}>Detection Time</span>
        <span style={fieldValue}>{alert.timestamp ? new Date(alert.timestamp).toLocaleString('en-IN') : '—'}</span>
      </div>
      <div style={fieldRow}>
        <span style={fieldLabel}>AI Confidence</span>
        <span style={{ ...fieldValue, fontWeight: 700 }}>{confPct}%</span>
      </div>
      <div style={fieldRow}>
        <span style={fieldLabel}>Detection Method</span>
        <span style={fieldValue}>YOLOv8 Object Detection — Temporal Confirmation (3-frame)</span>
      </div>

      {/* Location */}
      <div style={sectionHead}>2. Location</div>
      <div style={fieldRow}>
        <span style={fieldLabel}>GPS Coordinates</span>
        <span style={fieldValue}>
          {alert.gps ? `${alert.gps.lat.toFixed(6)}°N, ${alert.gps.lng.toFixed(6)}°E` : '—'}
        </span>
      </div>
      <div style={{ fontSize: 11, color: '#c05621', marginBottom: 10, padding: '6px 10px', background: '#fffaf0', border: '1px solid #fbd38d', borderRadius: 3 }}>
        ⚠ Note: GPS coordinates in this prototype are simulated for demonstration purposes.
        Real deployment would require hardware GPS integration with the bus fleet.
      </div>

      {/* Source */}
      <div style={sectionHead}>3. Source Vehicle</div>
      <div style={fieldRow}>
        <span style={fieldLabel}>Bus ID</span>
        <span style={{ ...fieldValue, fontFamily: 'monospace' }}>{alert.bus_id || '—'}</span>
      </div>
      <div style={fieldRow}>
        <span style={fieldLabel}>Data Source</span>
        <span style={fieldValue}>Public transport dashcam video</span>
      </div>

      {/* Evidence */}
      {alert.image_path && (
        <>
          <div style={sectionHead}>4. Evidence</div>
          <div style={{ border: '1px solid #e2e8f0', borderRadius: 3, overflow: 'hidden', maxWidth: 360, marginBottom: 8 }}>
            <img
              src={alert.image_path}
              alt="Pothole evidence"
              style={{ width: '100%', display: 'block' }}
              onError={(e) => { e.target.style.display = 'none' }}
            />
          </div>
          <p style={{ fontSize: 11, color: '#718096', marginTop: 4 }}>
            Cropped pothole region from dashcam frame. Saved as evidence by detection system.
          </p>
        </>
      )}

      {/* Recommended action */}
      <div style={sectionHead}>5. Recommended Action</div>
      <div style={{
        background: '#f0fff4',
        border: '1px solid #c6f6d5',
        borderRadius: 3,
        padding: '10px 14px',
        fontSize: 13,
        color: '#276749',
      }}>
        Field inspection recommended at the indicated GPS location.
        If confirmed, raise work order for road repair under PWD maintenance schedule.
      </div>

      {/* Footer */}
      <div style={{
        marginTop: 32,
        borderTop: '1px solid #e2e8f0',
        paddingTop: 12,
        fontSize: 10,
        color: '#a0aec0',
        display: 'flex',
        justifyContent: 'space-between',
      }}>
        <span>Generated by Urban Road Intelligence System — Automated Report</span>
        <span>{incidentId}</span>
      </div>
    </div>
  )
}
