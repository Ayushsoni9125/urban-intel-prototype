/**
 * IncidentReport.jsx
 * Generates a downloadable PDF incident report using jsPDF.
 * Triggered when user clicks "Generate Report" on a pothole alert.
 */

import { useRef, useState } from 'react'
import jsPDF from 'jspdf'

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

function getSeverity(conf) {
  const pct = (conf || 0) * 100
  if (pct >= 80) return { label: 'HIGH',   color: [220, 38, 38],   bg: [254, 226, 226] }
  if (pct >= 60) return { label: 'MEDIUM', color: [217, 119, 6],   bg: [254, 243, 199] }
  return               { label: 'LOW',    color: [37, 99, 235],    bg: [219, 234, 254] }
}

function getRepairAction(conf) {
  const pct = (conf || 0) * 100
  if (pct >= 80) return 'URGENT: Immediate field inspection and emergency patching required within 48 hours.'
  if (pct >= 60) return 'Schedule field inspection within 7 days and raise a PWD maintenance work order.'
  return 'Low priority — queue for routine inspection in the next maintenance cycle.'
}

export default function IncidentReport({ alert, onClose }) {
  if (!alert) return null

  const [generating, setGenerating] = useState(false)
  const previewRef = useRef(null)

  const confPct     = ((alert.confidence || 0) * 100).toFixed(1)
  const severity    = getSeverity(alert.confidence)
  const reportDate  = new Date().toLocaleDateString('en-IN', { year: 'numeric', month: 'long', day: '2-digit' })
  const incidentId  = `INC-${alert.id?.slice(0, 8).toUpperCase() || 'UNKNOWN'}`
  const generatedAt = new Date().toLocaleString('en-IN')

  // ─── PDF Generation ────────────────────────────────────────────────────────
  const handleDownloadPDF = async () => {
    setGenerating(true)
    try {
      const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
      const PW = 210   // page width mm
      const PH = 297   // page height mm
      const L  = 18    // left margin
      const R  = PW - L
      let y    = 0     // current Y position

      // ── Helper functions ──────────────────────────────────────────────────
      const setFont = (style = 'normal', size = 10, color = [26, 32, 44]) => {
        doc.setFont('helvetica', style)
        doc.setFontSize(size)
        doc.setTextColor(...color)
      }

      const drawLine = (x1, y1, x2, y2, color = [226, 232, 240], w = 0.3) => {
        doc.setDrawColor(...color)
        doc.setLineWidth(w)
        doc.line(x1, y1, x2, y2)
      }

      const fillRect = (x, ry, w, h, color) => {
        doc.setFillColor(...color)
        doc.rect(x, ry, w, h, 'F')
      }

      const text = (str, x, ry, opts = {}) => {
        doc.text(str, x, ry, opts)
      }

      // ── TOP HEADER BANNER ─────────────────────────────────────────────────
      fillRect(0, 0, PW, 36, [15, 23, 42])        // dark navy bar
      setFont('bold', 16, [255, 255, 255])
      text('URBAN ROAD INTELLIGENCE PLATFORM', L, 14)
      setFont('normal', 9, [148, 163, 184])
      text('Public Works Department — Road Monitoring Division', L, 21)
      text('AI-Assisted Road Defect Detection System  |  SIH 2026 Prototype', L, 27)

      // Incident ID badge (top right)
      fillRect(PW - 65, 8, 52, 12, [59, 130, 246])
      setFont('bold', 8, [255, 255, 255])
      text('INCIDENT REPORT', PW - 64, 15)
      setFont('normal', 7, [255, 255, 255])
      text(incidentId, PW - 64, 20)

      y = 44

      // ── SEVERITY BADGE ROW ────────────────────────────────────────────────
      fillRect(L, y, R - L, 12, severity.bg)
      doc.setDrawColor(...severity.color)
      doc.setLineWidth(0.5)
      doc.rect(L, y, R - L, 12)
      setFont('bold', 9, severity.color)
      text(`● SEVERITY: ${severity.label}  —  AI Confidence Score: ${confPct}%  —  Reported: ${reportDate}`, L + 3, y + 7.5)

      y += 18

      // ── SECTION 1: INCIDENT DETAILS ───────────────────────────────────────
      fillRect(L, y, R - L, 7, [241, 245, 249])
      setFont('bold', 8, [71, 85, 105])
      text('1.  INCIDENT DETAILS', L + 2, y + 5)
      y += 11

      const field = (label, value, highlight = false) => {
        if (y > PH - 30) { doc.addPage(); y = 20 }
        setFont('bold', 9, [71, 85, 105])
        text(label, L, y)
        setFont(highlight ? 'bold' : 'normal', 9, highlight ? [220, 38, 38] : [15, 23, 42])
        text(String(value), L + 60, y)
        drawLine(L, y + 2, R, y + 2)
        y += 9
      }

      field('Incident ID',         incidentId)
      field('Event Type',          (alert.event_type || 'pothole').replace('_', ' ').toUpperCase(), true)
      field('Detection Time',      formatTimestamp(alert.timestamp))
      field('Report Generated',    generatedAt)
      field('AI Confidence Score', `${confPct}%  (Threshold: 20% for mobile / 40% for dashcam)`)
      field('Detection Method',    'YOLOv8 Object Detection — Temporal 3-frame Confirmation')
      field('AI Model Used',       alert.source === 'mobile_camera' ? 'pothole_best.pt (mobile, conf ≥ 0.20)' : 'pothole_best.pt (dashcam, conf ≥ 0.40)')
      field('Data Source',         alert.source === 'mobile_camera' ? 'Live Mobile Camera (real-time capture)' : 'Bus Dashcam Video Feed')

      y += 4

      // ── SECTION 2: LOCATION ───────────────────────────────────────────────
      fillRect(L, y, R - L, 7, [241, 245, 249])
      setFont('bold', 8, [71, 85, 105])
      text('2.  LOCATION & GPS COORDINATES', L + 2, y + 5)
      y += 11

      const lat = alert.gps?.lat?.toFixed(6) ?? '—'
      const lng = alert.gps?.lng?.toFixed(6) ?? '—'
      field('GPS Latitude',         `${lat}° N`)
      field('GPS Longitude',        `${lng}° E`)
      field('Coordinate Format',   'WGS 84 (decimal degrees)')
      field('Maps Link',           `https://maps.google.com/?q=${lat},${lng}`)
      field('GPS Source',          alert.source === 'mobile_camera'
                                     ? 'Real GPS — browser geolocation API (phone hardware)'
                                     : 'Simulated GPS — demo prototype (not hardware GPS)')

      // GPS accuracy note
      y += 2
      fillRect(L, y, R - L, 10, [255, 251, 235])
      doc.setDrawColor(251, 191, 36)
      doc.setLineWidth(0.4)
      doc.rect(L, y, R - L, 10)
      setFont('normal', 8, [146, 64, 14])
      const gpsNote = alert.source === 'mobile_camera'
        ? '⚠  GPS from phone hardware (±5–15m accuracy outdoors). Coordinates are real.'
        : '⚠  GPS coordinates in video-based prototype are simulated for demonstration purposes.'
      text(gpsNote, L + 2, y + 6.5)
      y += 16

      // ── SECTION 3: SOURCE VEHICLE ─────────────────────────────────────────
      fillRect(L, y, R - L, 7, [241, 245, 249])
      setFont('bold', 8, [71, 85, 105])
      text('3.  SOURCE VEHICLE / DEVICE', L + 2, y + 5)
      y += 11

      field('Bus ID / Device',     alert.bus_id || '—')
      field('Vehicle Type',        alert.bus_id === 'MOBILE-CAM' ? 'Mobile Device (field inspection)' : 'Public Transport Bus')
      field('Onboard System',      'Urban Intel Edge Detection Unit v1.0')

      y += 4

      // ── SECTION 4: AI ANALYSIS METRICS ───────────────────────────────────
      fillRect(L, y, R - L, 7, [241, 245, 249])
      setFont('bold', 8, [71, 85, 105])
      text('4.  AI ANALYSIS METRICS', L + 2, y + 5)
      y += 11

      const confNum = parseFloat(confPct)
      field('Raw Confidence Score',    `${confPct}% (${(alert.confidence || 0).toFixed(4)} raw)`)
      field('Severity Classification', severity.label)
      field('Bounding Box Saved',      alert.image_path ? 'Yes — evidence image captured' : 'No image available')
      field('Model Version',           'YOLOv8 — pothole_best.pt (custom fine-tuned)')
      field('Training Dataset',        'Indian road pothole imagery (dashcam perspective)')
      field('Frame Sampling Rate',     'Every 5th frame processed (reduces CPU load by 80%)')
      field('False-Positive Control',  'Temporal confirmation — 3 consecutive frame detection required')
      field('Deduplication Radius',    '100 metres — same location alerts capped at 3 detections')

      y += 4

      // ── SECTION 5: RECOMMENDED ACTION ────────────────────────────────────
      fillRect(L, y, R - L, 7, [241, 245, 249])
      setFont('bold', 8, [71, 85, 105])
      text('5.  RECOMMENDED ACTION', L + 2, y + 5)
      y += 11

      fillRect(L, y, R - L, 16, [240, 253, 244])
      doc.setDrawColor(134, 239, 172)
      doc.setLineWidth(0.4)
      doc.rect(L, y, R - L, 16)
      setFont('bold', 9, [22, 101, 52])
      const actionLines = doc.splitTextToSize(getRepairAction(alert.confidence), R - L - 6)
      doc.text(actionLines, L + 3, y + 7)
      y += 22

      // Workflow steps
      setFont('bold', 8.5, [15, 23, 42])
      text('Repair Workflow:', L, y)
      y += 7

      const steps = [
        '① Forward this report to the Ward Engineer / Divisional Officer',
        '② Dispatch field inspection team to GPS coordinates within stated priority window',
        '③ Confirm severity on-site and photograph the defect',
        '④ Raise PWD maintenance work order and assign crew',
        '⑤ Mark location as "Under Repair" in the Urban Intel Dashboard',
        '⑥ Close the incident after repair verification and GPS photo upload',
      ]
      setFont('normal', 8.5, [30, 41, 59])
      for (const step of steps) {
        if (y > PH - 30) { doc.addPage(); y = 20 }
        text(step, L + 4, y)
        y += 7
      }

      y += 4

      // ── SECTION 6: EVIDENCE IMAGE ─────────────────────────────────────────
      if (alert.image_path) {
        if (y > PH - 80) { doc.addPage(); y = 20 }

        fillRect(L, y, R - L, 7, [241, 245, 249])
        setFont('bold', 8, [71, 85, 105])
        text('6.  EVIDENCE — AI-ANNOTATED FRAME', L + 2, y + 5)
        y += 11

        try {
          // Load image via fetch → base64
          const imgUrl = alert.image_path.startsWith('http')
            ? alert.image_path
            : `http://localhost:8000/images/${alert.image_path}`

          const resp = await fetch(imgUrl)
          const blob = await resp.blob()
          const b64  = await new Promise((res) => {
            const reader = new FileReader()
            reader.onload = () => res(reader.result)
            reader.readAsDataURL(blob)
          })

          const imgW = R - L
          const imgH = 60
          doc.addImage(b64, 'JPEG', L, y, imgW, imgH)
          y += imgH + 4
          setFont('normal', 8, [100, 116, 139])
          text('Fig 1: AI-annotated dashcam frame showing detected pothole with bounding box and confidence score.', L, y)
          y += 8
        } catch {
          setFont('italic', 8.5, [100, 116, 139])
          text('Evidence image could not be embedded (server may be offline).', L, y)
          text(`Image filename: ${alert.image_path}`, L, y + 6)
          y += 14
        }
      }

      // ── FOOTER ────────────────────────────────────────────────────────────
      const footerY = PH - 14
      drawLine(L, footerY - 2, R, footerY - 2, [226, 232, 240], 0.3)
      setFont('normal', 7.5, [148, 163, 184])
      text('Urban Road Intelligence System  |  AI-Automated Incident Report  |  SIH 2026 Prototype', L, footerY + 2)
      text(`${incidentId}  |  Generated: ${generatedAt}`, R, footerY + 2, { align: 'right' })
      setFont('normal', 7, [203, 213, 225])
      text('This report is auto-generated by an AI system. GPS coordinates should be verified by field personnel before action.', L, footerY + 8)

      // ── SAVE ──────────────────────────────────────────────────────────────
      doc.save(`${incidentId}_PotholReport.pdf`)
    } catch (err) {
      console.error('PDF generation error:', err)
      alert('Failed to generate PDF. Please try again.')
    } finally {
      setGenerating(false)
    }
  }

  // ─── Modal UI ──────────────────────────────────────────────────────────────
  const confNum = parseFloat(confPct)

  return (
    <>
      {/* Backdrop */}
      <div
        className="no-print"
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000 }}
      />

      {/* Modal */}
      <div
        className="no-print"
        style={{
          position: 'fixed', inset: '32px', maxWidth: 700,
          margin: '0 auto', zIndex: 1001, display: 'flex',
          flexDirection: 'column', background: '#fff',
          borderRadius: 6, boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
          overflow: 'hidden', fontFamily: 'Inter, Segoe UI, sans-serif',
        }}
      >
        {/* Toolbar */}
        <div style={{
          padding: '10px 16px', background: '#0f172a',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0,
        }}>
          <div>
            <span style={{ color: '#fff', fontSize: 13, fontWeight: 700 }}>
              Incident Report — {incidentId}
            </span>
            <span style={{ marginLeft: 12, fontSize: 11, color: '#64748b' }}>
              {formatTimestamp(alert.timestamp)}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              id="download-pdf-btn"
              onClick={handleDownloadPDF}
              disabled={generating}
              style={{
                padding: '6px 16px', background: generating ? '#374151' : '#2563eb',
                color: '#fff', border: 'none', borderRadius: 4,
                fontSize: 12, fontWeight: 700, cursor: generating ? 'wait' : 'pointer',
                fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              {generating ? '⏳ Generating PDF…' : '⬇ Download PDF'}
            </button>
            <button
              id="close-report-btn"
              onClick={onClose}
              style={{
                padding: '6px 12px', background: 'transparent',
                color: '#94a3b8', border: '1px solid #334155',
                borderRadius: 4, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              ✕ Close
            </button>
          </div>
        </div>

        {/* Preview inside modal */}
        <div ref={previewRef} style={{ flex: 1, overflowY: 'auto', background: '#f8fafc' }}>
          <div style={{ padding: '28px 36px', maxWidth: 640, margin: '0 auto', background: '#fff', minHeight: '100%' }}>

            {/* Header */}
            <div style={{ borderBottom: '3px solid #0f172a', paddingBottom: 14, marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em' }}>Urban Road Intelligence</div>
                <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>Public Works Department — Road Monitoring Division</div>
                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 1 }}>AI-Assisted Road Defect Detection System | SIH 2026 Prototype</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ background: '#0f172a', color: '#fff', padding: '3px 10px', borderRadius: 3, fontSize: 10, fontWeight: 700, letterSpacing: '0.06em' }}>INCIDENT REPORT</div>
                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 4 }}>{reportDate}</div>
              </div>
            </div>

            {/* Incident ID */}
            <div style={{ background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 4, padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#64748b' }}>INCIDENT ID</span>
              <span style={{ fontSize: 15, fontWeight: 800, color: '#0f172a', letterSpacing: '0.05em' }}>{incidentId}</span>
            </div>

            {/* Severity badge */}
            <div style={{ background: `rgb(${severity.bg.join(',')})`, border: `1px solid rgb(${severity.color.join(',')})`, borderRadius: 4, padding: '8px 12px', marginBottom: 20, display: 'flex', gap: 20, alignItems: 'center' }}>
              <span style={{ fontWeight: 800, fontSize: 13, color: `rgb(${severity.color.join(',')})` }}>⬤ SEVERITY: {severity.label}</span>
              <span style={{ fontSize: 12, color: '#374151' }}>Confidence: <strong>{confPct}%</strong></span>
              <span style={{ fontSize: 12, color: '#374151' }}>Source: <strong>{alert.source === 'mobile_camera' ? 'Mobile Camera' : 'Dashcam Video'}</strong></span>
            </div>

            {/* Field group helper */}
            {[
              {
                title: '1. Incident Details',
                fields: [
                  ['Event Type', (alert.event_type || 'pothole').replace('_', ' ').toUpperCase()],
                  ['Detection Time', formatTimestamp(alert.timestamp)],
                  ['AI Confidence Score', `${confPct}%`],
                  ['Detection Method', 'YOLOv8 Object Detection — Temporal 3-frame Confirmation'],
                  ['AI Model', 'pothole_best.pt (custom fine-tuned YOLO)'],
                  ['Data Source', alert.source === 'mobile_camera' ? 'Live Mobile Camera' : 'Bus Dashcam Video'],
                ],
              },
              {
                title: '2. Location',
                fields: [
                  ['GPS Latitude', `${alert.gps?.lat?.toFixed(6) ?? '—'}° N`],
                  ['GPS Longitude', `${alert.gps?.lng?.toFixed(6) ?? '—'}° E`],
                  ['Coordinate Format', 'WGS 84 (decimal degrees)'],
                  ['GPS Source', alert.source === 'mobile_camera' ? 'Real GPS (phone hardware)' : 'Simulated GPS (prototype demo)'],
                ],
              },
              {
                title: '3. Source Vehicle / Device',
                fields: [
                  ['Bus ID / Device', alert.bus_id || '—'],
                  ['Vehicle Type', alert.bus_id === 'MOBILE-CAM' ? 'Mobile Device (field inspection)' : 'Public Transport Bus'],
                  ['Onboard System', 'Urban Intel Edge Detection Unit v1.0'],
                ],
              },
              {
                title: '4. AI Analysis Metrics',
                fields: [
                  ['Raw Confidence', `${confPct}% (${(alert.confidence || 0).toFixed(4)} raw score)`],
                  ['Severity Level', severity.label],
                  ['Evidence Saved', alert.image_path ? 'Yes — annotated JPEG captured' : 'No image'],
                  ['Dedup Radius', '100 metres (same-location cap: 3 detections)'],
                  ['3-Frame Confirmation', 'Enabled — reduces false positives'],
                ],
              },
            ].map(({ title, fields }) => (
              <div key={title} style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 10, fontWeight: 800, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid #e2e8f0', paddingBottom: 5, marginBottom: 10 }}>{title}</div>
                {fields.map(([label, value]) => (
                  <div key={label} style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: '3px 12px', marginBottom: 7, fontSize: 12 }}>
                    <span style={{ fontWeight: 600, color: '#64748b' }}>{label}</span>
                    <span style={{ color: '#0f172a' }}>{value}</span>
                  </div>
                ))}
              </div>
            ))}

            {/* Evidence image */}
            {alert.image_path && (
              <div style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 10, fontWeight: 800, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid #e2e8f0', paddingBottom: 5, marginBottom: 10 }}>5. Evidence — AI-Annotated Frame</div>
                <div style={{ border: '1px solid #e2e8f0', borderRadius: 4, overflow: 'hidden', maxWidth: 420 }}>
                  <img
                    src={alert.image_path.startsWith('http') ? alert.image_path : `http://localhost:8000/images/${alert.image_path}`}
                    alt="Pothole evidence"
                    style={{ width: '100%', display: 'block' }}
                    onError={(e) => { e.target.style.display = 'none' }}
                  />
                </div>
                <p style={{ fontSize: 10, color: '#94a3b8', marginTop: 5 }}>AI-annotated frame with bounding box and confidence label. Saved automatically by detection system.</p>
              </div>
            )}

            {/* Recommended action */}
            <div style={{ marginBottom: 18 }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid #e2e8f0', paddingBottom: 5, marginBottom: 10 }}>6. Recommended Action</div>
              <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 4, padding: '10px 14px', fontSize: 12, color: '#166534', fontWeight: 600 }}>
                {getRepairAction(alert.confidence)}
              </div>
            </div>

            {/* Footer */}
            <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: 10, marginTop: 20, display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#94a3b8' }}>
              <span>Urban Road Intelligence System — Automated Report</span>
              <span>{incidentId}</span>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
