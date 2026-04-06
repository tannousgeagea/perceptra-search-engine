import { useEffect, useState } from 'react'
import type { WasteCamera } from '../../types/api'
import { listWasteCameras } from '../../api/client'
import { useCameraStream } from './hooks/useCameraStream'

/**
 * Minimal standalone view for iframe embedding.
 * Activated via /wastevision?embed=1&camera={uuid}
 */
export default function EmbedWidget() {
  const params = new URLSearchParams(window.location.search)
  const cameraUuid = params.get('camera')

  const [camera, setCamera] = useState<WasteCamera | null>(null)
  const { latestInspection, connected } = useCameraStream(cameraUuid)

  useEffect(() => {
    if (!cameraUuid) return
    listWasteCameras()
      .then(r => {
        const found = r.data.items.find(c => c.camera_uuid === cameraUuid)
        setCamera(found ?? null)
      })
      .catch(() => {})
  }, [cameraUuid])

  const risk = latestInspection?.overall_risk ?? camera?.last_risk_level ?? 'low'
  const riskColors = { low: '#00e676', medium: '#ffea00', high: '#f5a623', critical: '#ff1744' }
  const riskColor = riskColors[risk as keyof typeof riskColors] ?? '#4e5a73'

  return (
    <div style={{
      width: '100%', height: '100%', minHeight: 200,
      background: '#040608', color: '#e2e8f4',
      fontFamily: "'JetBrains Mono', monospace",
      border: `2px solid ${riskColor}33`,
      borderRadius: 6, overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 14px', background: '#08090f', borderBottom: `1px solid #131926`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 7, height: 7, borderRadius: '50%',
            background: connected ? '#00e676' : '#4e5a73',
          }} />
          <span style={{ fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#8b97b5' }}>
            {camera?.name ?? 'WasteVision'}
          </span>
        </div>
        <span style={{
          background: `${riskColor}22`, color: riskColor,
          border: `1px solid ${riskColor}44`,
          padding: '2px 8px', borderRadius: 3,
          fontSize: '0.62rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase',
        }}>
          {risk.toUpperCase()}
        </span>
      </div>

      {/* Body */}
      {latestInspection ? (
        <div style={{ padding: 14 }}>
          {/* Composition mini bars */}
          {Object.entries(latestInspection.waste_composition).map(([mat, val]) => {
            if ((val as number) < 2) return null
            return (
              <div key={mat} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                <span style={{ width: 60, fontSize: '0.6rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#8b97b5' }}>
                  {mat.replace('_', '-')}
                </span>
                <div style={{ flex: 1, height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${val}%`, background: mat === 'hazardous' ? '#ef4444' : '#0ea5e9', borderRadius: 2 }} />
                </div>
                <span style={{ width: 30, textAlign: 'right', fontSize: '0.6rem', color: '#e2e8f4' }}>{Math.round(val as number)}%</span>
              </div>
            )
          })}

          {/* Top alert */}
          {latestInspection.contamination_alerts?.[0] && (
            <div style={{
              marginTop: 10, padding: '6px 10px',
              background: 'rgba(255,23,68,0.1)', border: '1px solid rgba(255,23,68,0.3)',
              borderRadius: 3, fontSize: '0.65rem',
            }}>
              ⚠ {latestInspection.contamination_alerts[0].item} — {latestInspection.contamination_alerts[0].action}
            </div>
          )}

          {/* Inspector note */}
          <div style={{ marginTop: 8, fontSize: '0.62rem', color: '#8b97b5', fontStyle: 'italic' }}>
            {latestInspection.inspector_note}
          </div>
        </div>
      ) : (
        <div style={{ padding: 24, textAlign: 'center', color: '#4e5a73', fontSize: '0.68rem' }}>
          {camera ? 'Waiting for inspection data...' : 'Camera not found'}
        </div>
      )}
    </div>
  )
}
