/**
 * MapView.jsx — Fixed layer isolation
 *
 * Root cause of "same heatmap" bug:
 *  - HeatmapLayer had no `key` prop, so React reused the same instance
 *    when toggling layers, the cleanup/remount never fired properly.
 *  - Both layers were stacking and the traffic one always won visually.
 *
 * Fix:
 *  - Give each HeatmapLayer a stable unique `key` based on layer type
 *  - Only mount the layer that matches the active selection
 *  - Clear visible distinction: traffic = blue→green→amber→red broad route
 *                               pothole = tight orange→red hotspots
 */

import { useEffect, useRef, useState, useMemo } from 'react'
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMap,
} from 'react-leaflet'
import L from 'leaflet'

// Fix Vite's broken Leaflet default icon paths
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

// Local leaflet-heat bundle
import '../lib/leaflet-heat.js'

// ----------------------------------------------------------------
// Custom pothole marker icon
// ----------------------------------------------------------------
const potholeIcon = L.divIcon({
  className: '',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
  popupAnchor: [0, -16],
  html: `<div style="
    width:24px;height:24px;background:#c53030;
    border:2.5px solid #fff;border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    box-shadow:0 2px 6px rgba(0,0,0,0.45);cursor:pointer;">
    <div style="width:8px;height:8px;background:#fff;border-radius:50%;"></div>
  </div>`,
})


// ----------------------------------------------------------------
// HeatmapLayer — isolated per layer type via `key` prop
// ----------------------------------------------------------------
function HeatmapLayer({ points, options, layerId }) {
  const map = useMap()
  const layerRef = useRef(null)

  useEffect(() => {
    // Always clean up any existing layer first
    if (layerRef.current) {
      try { map.removeLayer(layerRef.current) } catch (_) {}
      layerRef.current = null
    }

    if (!points || points.length === 0) return
    if (!L.heatLayer) {
      console.warn('L.heatLayer not available')
      return
    }

    const heat = L.heatLayer(points, options)
    heat.addTo(map)
    layerRef.current = heat

    return () => {
      if (layerRef.current) {
        try { map.removeLayer(layerRef.current) } catch (_) {}
        layerRef.current = null
      }
    }
  // Use JSON.stringify of first/last point as stable dep instead of the array ref
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, layerId, points.length])

  return null
}

// ----------------------------------------------------------------
// Heatmap visual configs — deliberately distinct
// ----------------------------------------------------------------

// Traffic: broad spread, cool→warm gradient (blue → green → amber → red)
// Shows vehicle DENSITY along the route — wide radius for broad view
const TRAFFIC_OPTIONS = {
  radius: 55,
  blur: 40,
  maxZoom: 17,
  max: 1.0,
  minOpacity: 0.3,
  gradient: {
    0.0: '#1e40af',   // dark blue  — very low traffic
    0.3: '#0ea5e9',   // sky blue   — low
    0.5: '#10b981',   // green      — moderate
    0.75: '#f59e0b',  // amber      — high
    1.0: '#dc2626',   // red        — very high congestion
  },
}

// Pothole: tight hotspot, warm orange→red gradient
// Shows LOCATION precision — small radius for pinpoint accuracy
const POTHOLE_OPTIONS = {
  radius: 30,
  blur: 20,
  maxZoom: 17,
  max: 1.0,
  minOpacity: 0.5,
  gradient: {
    0.0: '#fde68a',   // light yellow — lower confidence
    0.4: '#f97316',   // orange       — medium confidence
    0.8: '#dc2626',   // red          — high confidence
    1.0: '#7f1d1d',   // dark red     — very high (multiple potholes nearby)
  },
}

// ----------------------------------------------------------------
// Main MapView
// ----------------------------------------------------------------
const DELHI_CENTER = [28.6139, 77.2090]
const DEFAULT_ZOOM = 14

export default function MapView({ potholeAlerts, trafficData, onMarkerClick }) {
  const [activeLayer, setActiveLayer] = useState('traffic')
  const [isFullscreen, setIsFullscreen] = useState(false)

  // Normalise traffic heat points — larger point array = route density
  const trafficPoints = useMemo(() => {
    if (!trafficData || trafficData.length === 0) return []
    const maxCount = Math.max(...trafficData.map(p => p.vehicle_count), 1)
    return trafficData.map(p => [
      p.lat,
      p.lng,
      Math.min(p.vehicle_count / maxCount, 1.0),
    ])
  }, [trafficData])

  // Pothole heat points — confidence as intensity
  const potholePoints = useMemo(() => {
    if (!potholeAlerts || potholeAlerts.length === 0) return []
    return potholeAlerts
      .filter(a => a.gps)
      .map(a => [a.gps.lat, a.gps.lng, Math.max(a.confidence || 0.6, 0.5)])
  }, [potholeAlerts])

  const showTraffic     = activeLayer === 'traffic'     || activeLayer === 'both'
  const showPothole     = activeLayer === 'pothole'     || activeLayer === 'both'


  const btn = (layer) => ({
    border: '1px solid',
    borderColor: activeLayer === layer ? '#1a202c' : '#d1d5db',
    borderRadius: 3,
    padding: '5px 13px',
    fontSize: 12,
    fontWeight: 500,
    cursor: 'pointer',
    fontFamily: 'inherit',
    background: activeLayer === layer ? '#1a202c' : '#fff',
    color: activeLayer === layer ? '#fff' : '#4a5568',
    transition: 'background 0.15s, color 0.15s',
  })

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      ...(isFullscreen ? {
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        background: '#fff'
      } : {})
    }}>

      {/* Toolbar */}
      <div style={{
        background: '#fff',
        borderBottom: '1px solid #d1d5db',
        padding: '8px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexShrink: 0,
        flexWrap: 'wrap',
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#718096', marginRight: 4, letterSpacing: '0.05em' }}>
          MAP LAYER:
        </span>
        <button id="layer-traffic" style={btn('traffic')} onClick={() => setActiveLayer('traffic')}>
          🚦 Traffic Heatmap
        </button>
        <button id="layer-pothole" style={btn('pothole')} onClick={() => setActiveLayer('pothole')}>
          🕳 Pothole Heatmap
        </button>

        <button id="layer-both" style={btn('both')} onClick={() => setActiveLayer('both')}>
          All Layers
        </button>

        {/* Legend — changes based on active layer */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 14, fontSize: 11, color: '#718096' }}>
          {(activeLayer === 'traffic' || activeLayer === 'both') && (
            <>
              <span style={{ fontWeight: 600, color: '#374151' }}>Traffic:</span>
              <span><span style={{ color: '#1e40af', fontWeight: 700 }}>■</span> Low</span>
              <span><span style={{ color: '#10b981', fontWeight: 700 }}>■</span> Moderate</span>
              <span><span style={{ color: '#f59e0b', fontWeight: 700 }}>■</span> High</span>
              <span><span style={{ color: '#dc2626', fontWeight: 700 }}>■</span> Congestion</span>
            </>
          )}
          {(activeLayer === 'pothole' || activeLayer === 'both') && (
            <>
              <span style={{ fontWeight: 600, color: '#374151', marginLeft: activeLayer === 'both' ? 8 : 0 }}>Potholes:</span>
              <span><span style={{ color: '#f97316', fontWeight: 700 }}>■</span> Detected</span>
              <span><span style={{ color: '#dc2626', fontWeight: 700 }}>■</span> High severity</span>
              <span>🔴 Marker = confirmed</span>
            </>
          )}
        </div>

        {/* Fullscreen Toggle */}
        <button
          onClick={() => setIsFullscreen(!isFullscreen)}
          style={{
            marginLeft: 8,
            border: '1px solid #d1d5db',
            borderRadius: 3,
            padding: '4px 10px',
            fontSize: 11,
            fontWeight: 600,
            background: '#f3f4f6',
            color: '#374151',
            cursor: 'pointer',
          }}
        >
          {isFullscreen ? '↘ Exit Fullscreen' : '↗ Fullscreen'}
        </button>
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
        <MapContainer
          center={DELHI_CENTER}
          zoom={DEFAULT_ZOOM}
          style={{ height: '100%', width: '100%' }}
          zoomControl
        >
          <TileLayer
            attribution='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />

          {/*
            KEY PROP IS CRITICAL:
            'traffic-heat' and 'pothole-heat' ensure React treats these as
            completely separate component instances. Without distinct keys,
            React reuses the same HeatmapLayer instance when toggling and
            the cleanup effect never fires — causing both to look identical.
          */}
          {showTraffic && trafficPoints.length > 0 && (
            <HeatmapLayer
              key="traffic-heat"
              layerId="traffic"
              points={trafficPoints}
              options={TRAFFIC_OPTIONS}
            />
          )}

          {showPothole && potholePoints.length > 0 && (
            <HeatmapLayer
              key="pothole-heat"
              layerId="pothole"
              points={potholePoints}
              options={POTHOLE_OPTIONS}
            />
          )}

          {/*
            Pothole markers are only shown when Pothole or Both Layers
            is active. On Traffic Heatmap they are hidden to avoid confusion
            — the user should not see pothole popups when viewing traffic data.
          */}
          {showPothole && (potholeAlerts || []).map((alert, idx) => {
            if (!alert.gps) return null
            const conf = ((alert.confidence || 0) * 100).toFixed(0)
            const ts = alert.timestamp
              ? new Date(alert.timestamp).toLocaleString('en-IN')
              : 'N/A'
            return (
              <Marker
                key={alert.id || idx}
                position={[alert.gps.lat, alert.gps.lng]}
                icon={potholeIcon}
                eventHandlers={{ click: () => onMarkerClick?.(alert) }}
              >
                <Popup>
                  <div style={{ fontSize: 13, minWidth: 190 }}>
                    <div style={{ fontWeight: 700, color: '#c53030', marginBottom: 6 }}>
                      🔴 Pothole Confirmed
                    </div>
                    <div><b>Confidence:</b> {conf}%</div>
                    <div><b>Bus:</b> {alert.bus_id || '—'}</div>
                    <div><b>Time:</b> {ts}</div>
                    <div style={{ fontSize: 10, color: '#999', marginTop: 4 }}>
                      {alert.gps.lat.toFixed(5)}, {alert.gps.lng.toFixed(5)}<br/>
                      <i>(Simulated GPS)</i>
                    </div>
                    {alert.image_path && (
                      <img
                        src={alert.image_path}
                        alt="evidence"
                        style={{ width: '100%', marginTop: 8, borderRadius: 3 }}
                        onError={e => { e.target.style.display = 'none' }}
                      />
                    )}
                  </div>
                </Popup>
              </Marker>
            )
          })}

        </MapContainer>

        {/* Layer description overlay */}
        <div style={{
          position: 'absolute',
          top: 10,
          right: 10,
          zIndex: 1000,
          background: 'rgba(255,255,255,0.92)',
          padding: '6px 10px',
          fontSize: 11,
          color: '#374151',
          borderRadius: 4,
          border: '1px solid #e5e7eb',
          maxWidth: 180,
          lineHeight: 1.4,
          pointerEvents: 'none',
        }}>
          {activeLayer === 'traffic' && (
            <>
              <b>Traffic Density</b><br/>
              44 density points from<br/>~5,757 vehicles detected.<br/>
              <span style={{ color: '#888', fontSize: 10 }}>Blue→Red = Low→High</span>
            </>
          )}
          {activeLayer === 'pothole' && (
            <>
              <b>Pothole Hotspots</b><br/>
              5 confirmed potholes.<br/>
              Tight radius = precise<br/>defect locations.<br/>
              <span style={{ color: '#888', fontSize: 10 }}>Orange→Dark Red = severity</span>
            </>
          )}
          {activeLayer === 'both' && (
            <>
              <b>Combined View</b><br/>
              Blue = traffic density<br/>
              Orange/Red = potholes<br/>
              <span style={{ color: '#888', fontSize: 10 }}>Note: scales differ per layer</span>
            </>
          )}
        </div>

        {/* GPS notice */}
        <div style={{
          position: 'absolute',
          bottom: 28,
          left: 10,
          zIndex: 1000,
          background: 'rgba(255,255,255,0.88)',
          padding: '3px 8px',
          fontSize: 10,
          color: '#555',
          borderRadius: 3,
          border: '1px solid #ccc',
          pointerEvents: 'none',
        }}>
          ⚠ GPS: Simulated (Demo Prototype)
        </div>
      </div>
    </div>
  )
}
