/**
 * Header.jsx
 * Government-style top navigation bar.
 */

export default function Header({ apiStatus, lastUpdated }) {
  const statusConfig = {
    active:      { color: '#276749', bg: '#f0fff4', dot: '#38a169', label: 'System Active' },
    error:       { color: '#c53030', bg: '#fff5f5', dot: '#fc8181', label: 'API Offline' },
    connecting:  { color: '#975a16', bg: '#fffaf0', dot: '#f6ad55', label: 'Connecting...' },
  }

  const s = statusConfig[apiStatus] || statusConfig.connecting

  const formatTime = (date) => {
    if (!date) return '—'
    return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  return (
    <header
      style={{
        background: '#1a202c',
        borderBottom: '3px solid #2c5282',
        color: '#fff',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        height: '60px',
        flexShrink: 0,
      }}
    >
      {/* Left — Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* Road icon */}
        <div style={{
          width: 36, height: 36,
          background: '#2c5282',
          borderRadius: 4,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#90cdf4" strokeWidth="2">
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 17, fontWeight: 700, letterSpacing: '-0.02em', color: '#fff' }}>
            Urban Road Intelligence
          </h1>
          <p style={{ margin: 0, fontSize: 11, color: '#a0aec0', marginTop: 1 }}>
            Real-time road monitoring using public transport fleet
          </p>
        </div>
      </div>

      {/* Right — Status indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
        {/* Last updated */}
        <span style={{ fontSize: 11, color: '#718096' }}>
          {lastUpdated ? `Updated: ${formatTime(lastUpdated)}` : 'Awaiting data...'}
        </span>

        {/* Status pill */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: s.bg,
          border: `1px solid ${s.dot}`,
          borderRadius: 20,
          padding: '3px 10px 3px 8px',
        }}>
          {/* Animated dot */}
          <span style={{
            display: 'inline-block',
            width: 7, height: 7,
            borderRadius: '50%',
            background: s.dot,
            flexShrink: 0,
          }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: s.color }}>
            {s.label}
          </span>
        </div>


      </div>
    </header>
  )
}
