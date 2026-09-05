/**
 * StatsBar.jsx
 * A row of simple summary statistics cards.
 * Values come from live API data — no fake numbers.
 */

const StatCard = ({ label, value, subtitle, color }) => (
  <div style={{
    flex: 1,
    borderRight: '1px solid var(--color-border)',
    padding: '14px 20px',
    minWidth: 120,
  }}>
    <div style={{
      fontSize: 26,
      fontWeight: 700,
      color: color || 'var(--color-text-primary)',
      lineHeight: 1,
      fontVariantNumeric: 'tabular-nums',
    }}>
      {value ?? '—'}
    </div>
    <div style={{
      fontSize: 12,
      color: 'var(--color-text-secondary)',
      marginTop: 4,
      fontWeight: 500,
      textTransform: 'uppercase',
      letterSpacing: '0.04em',
    }}>
      {label}
    </div>
    {subtitle && (
      <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>
        {subtitle}
      </div>
    )}
  </div>
)

export default function StatsBar({ stats, alertCount, potholeCount }) {
  const totalVehicles = stats?.vehicles_detected ?? 0
  const trafficEvents = stats?.traffic_events ?? 0
  const activeBuses   = stats?.active_buses ?? 0
  const congestion    = stats?.congestion_events ?? 0

  return (
    <div style={{
      background: '#fff',
      borderBottom: '1px solid var(--color-border)',
      display: 'flex',
      flexWrap: 'wrap',
      overflow: 'hidden',
    }}>
      <StatCard
        label="Potholes Detected"
        value={potholeCount}
        subtitle="Confirmed (YOLO + 3-frame)"
        color={potholeCount > 0 ? 'var(--color-alert-red)' : undefined}
      />

      <StatCard
        label="Traffic Events"
        value={trafficEvents}
        subtitle="Density data points"
      />
      <StatCard
        label="Vehicles Detected"
        value={totalVehicles.toLocaleString('en-IN')}
        subtitle="Cars, trucks, buses, bikes"
      />
      <StatCard
        label="Active Buses"
        value={activeBuses}
        subtitle="Fleet reporting"
      />
      <StatCard
        label="Congestion Alerts"
        value={congestion}
        color={congestion > 0 ? 'var(--color-alert-orange)' : undefined}
        subtitle="High-density events"
      />
      <div style={{
        padding: '14px 16px',
        display: 'flex',
        alignItems: 'center',
        fontSize: 10,
        color: 'var(--color-text-muted)',
        maxWidth: 180,
        lineHeight: 1.4,
      }}>
        ⚠ GPS coordinates in this prototype are simulated for demonstration. No real hardware GPS is used.
      </div>
    </div>
  )
}
