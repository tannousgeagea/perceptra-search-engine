import { useState } from 'react'
import { Camera, Wifi, WifiOff, ZapOff } from 'lucide-react'
import type { WasteCamera, WasteInspection, WasteContaminationItem } from '../../types/api'
import { useCameraStream } from './hooks/useCameraStream'

// Maps location_in_frame to CSS position percentages
const ZONE_POSITIONS: Record<string, React.CSSProperties> = {
  'top-left':     { top: '5%',  left: '5%',  width: '35%', height: '40%' },
  'top-right':    { top: '5%',  left: '60%', width: '35%', height: '40%' },
  'center':       { top: '30%', left: '30%', width: '40%', height: '40%' },
  'bottom-left':  { top: '55%', left: '5%',  width: '35%', height: '40%' },
  'bottom-right': { top: '55%', left: '60%', width: '35%', height: '40%' },
}

function RiskBadge({ risk }: { risk: string }) {
  return (
    <span className={`wv-risk-badge ${risk}`}>
      {risk === 'critical' ? '⚠ ' : ''}{risk.toUpperCase()}
    </span>
  )
}

function CameraCell({
  camera,
  onClick,
}: {
  camera: WasteCamera
  onClick: () => void
}) {
  const { latestInspection, connected } = useCameraStream(
    camera.is_active ? camera.camera_uuid : null
  )

  const risk = latestInspection?.overall_risk ?? (camera.last_risk_level || 'low')

  return (
    <div className={`wv-camera-cell risk-${risk}`} onClick={onClick}>
      {/* Header */}
      <div className="wv-camera-header">
        <span className="wv-camera-name">{camera.name}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {camera.status === 'streaming' && connected
            ? <Wifi size={11} color="var(--wv-green)" />
            : <WifiOff size={11} color="var(--text-muted)" />
          }
          <RiskBadge risk={risk} />
        </div>
      </div>

      {/* Frame placeholder (no actual JPEG delivery in this implementation — shows last inspection data) */}
      <div className="wv-camera-placeholder">
        <Camera size={28} color="var(--wv-border-bright)" />
        <span>{camera.location}</span>
        {latestInspection && (
          <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>
            seq #{latestInspection.sequence_no}
          </span>
        )}
        {!camera.is_active && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)' }}>
            <ZapOff size={12} />
            <span>Inactive</span>
          </div>
        )}
      </div>

      {/* Contamination zone overlays */}
      {latestInspection?.contamination_alerts?.map((item, i) => {
        const pos = ZONE_POSITIONS[item.location_in_frame]
        if (!pos) return null
        return (
          <div
            key={i}
            className={`wv-zone-overlay ${item.severity}`}
            style={{ ...pos, position: 'absolute' }}
            title={`${item.item} — ${item.action}`}
          />
        )
      })}

      {/* Line blockage indicator */}
      {latestInspection?.line_blockage && (
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: 'rgba(255,23,68,0.7)', color: '#fff',
          fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.12em',
          textAlign: 'center', padding: '4px',
          textTransform: 'uppercase',
        }}>
          ⛔ LINE BLOCKED
        </div>
      )}

      {/* Inspector note tooltip */}
      {latestInspection?.inspector_note && (
        <div style={{
          position: 'absolute', bottom: latestInspection.line_blockage ? 24 : 0,
          left: 0, right: 0,
          background: 'rgba(4,6,8,0.8)', color: 'var(--text-secondary)',
          fontSize: '0.6rem', padding: '4px 8px',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {latestInspection.inspector_note}
        </div>
      )}
    </div>
  )
}

type GridSize = 2 | 3 | 4

export default function CameraGrid({ cameras }: { cameras: WasteCamera[] }) {
  const [gridSize, setGridSize] = useState<GridSize>(2)
  const [focusedCamera, setFocusedCamera] = useState<WasteCamera | null>(null)

  return (
    <div>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 16px', borderBottom: '1px solid var(--wv-border)',
      }}>
        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
          {cameras.filter(c => c.status === 'streaming').length} / {cameras.length} STREAMING
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          {([2, 3, 4] as GridSize[]).map(n => (
            <button
              key={n}
              className={`wv-btn wv-btn-ghost`}
              style={{ padding: '4px 10px', fontSize: '0.62rem', ...(gridSize === n ? { color: 'var(--wv-green)', borderColor: 'var(--wv-green)' } : {}) }}
              onClick={() => setGridSize(n)}
            >
              {n}×{n}
            </button>
          ))}
        </div>
      </div>

      {cameras.length === 0 ? (
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
          No cameras registered. Add one in the MANAGE tab.
        </div>
      ) : (
        <div className={`wv-camera-grid grid-${gridSize}`}>
          {cameras.map(cam => (
            <CameraCell
              key={cam.camera_uuid}
              camera={cam}
              onClick={() => setFocusedCamera(cam)}
            />
          ))}
        </div>
      )}

      {/* Focus modal */}
      {focusedCamera && (
        <FocusModal camera={focusedCamera} onClose={() => setFocusedCamera(null)} />
      )}
    </div>
  )
}

function FocusModal({ camera, onClose }: { camera: WasteCamera; onClose: () => void }) {
  const { latestInspection } = useCameraStream(camera.is_active ? camera.camera_uuid : null)
  const risk = latestInspection?.overall_risk ?? (camera.last_risk_level || 'low')

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(4,6,8,0.92)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--wv-panel)', border: '1px solid var(--wv-border-bright)',
          borderRadius: 6, width: '80vw', maxWidth: 820,
          padding: 24,
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, letterSpacing: '0.08em' }}>{camera.name}</div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>{camera.location}</div>
          </div>
          <span className={`wv-risk-badge ${risk}`}>{risk.toUpperCase()}</span>
        </div>

        {latestInspection ? (
          <InspectionDetail inspection={latestInspection} />
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', textAlign: 'center', padding: 32 }}>
            Waiting for inspection data...
          </div>
        )}

        <div style={{ textAlign: 'right', marginTop: 20 }}>
          <button className="wv-btn wv-btn-ghost" onClick={onClose}>CLOSE</button>
        </div>
      </div>
    </div>
  )
}

function InspectionDetail({ inspection }: { inspection: WasteInspection }) {
  const comp = inspection.waste_composition
  const materials = Object.entries(comp) as [string, number][]
  const colorMap: Record<string, string> = {
    plastic: '#0ea5e9', paper: '#a3e635', glass: '#38bdf8',
    metal: '#94a3b8', organic: '#86efac', e_waste: '#f97316',
    hazardous: '#ef4444', other: '#64748b',
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      {/* Composition */}
      <div>
        <div style={{ fontSize: '0.62rem', letterSpacing: '0.12em', color: 'var(--text-muted)', marginBottom: 12, textTransform: 'uppercase' }}>
          Waste Composition
        </div>
        {materials.map(([k, v]) => (
          <div key={k} className="wv-comp-bar-row">
            <span className="wv-comp-label">{k.replace('_', '-')}</span>
            <div className="wv-comp-track">
              <div
                className="wv-comp-fill"
                style={{ width: `${v}%`, background: colorMap[k] || '#64748b' }}
              />
            </div>
            <span className="wv-comp-pct">{Math.round(v)}%</span>
          </div>
        ))}
      </div>

      {/* Alerts + meta */}
      <div>
        <div style={{ fontSize: '0.62rem', letterSpacing: '0.12em', color: 'var(--text-muted)', marginBottom: 12, textTransform: 'uppercase' }}>
          Contamination Alerts ({inspection.contamination_alerts?.length ?? 0})
        </div>
        {inspection.contamination_alerts?.map((a, i) => (
          <div key={i} style={{
            padding: '8px 10px', marginBottom: 6,
            background: 'var(--wv-surface)', borderRadius: 3,
            borderLeft: `3px solid ${a.severity === 'critical' ? 'var(--wv-red)' : 'var(--wv-amber)'}`,
          }}>
            <div style={{ fontWeight: 600, fontSize: '0.72rem' }}>{a.item}</div>
            <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: 2 }}>
              {a.location_in_frame} · {a.action}
            </div>
          </div>
        ))}

        {inspection.line_blockage && (
          <div style={{
            padding: '8px 10px', background: 'var(--wv-red-dim)',
            border: '1px solid rgba(255,23,68,0.3)', borderRadius: 3,
            color: 'var(--wv-red)', fontSize: '0.72rem', fontWeight: 700,
          }}>
            ⛔ LINE BLOCKED — Stop conveyor immediately
          </div>
        )}

        <div className="wv-inspector-note" style={{ marginTop: 12 }}>
          {inspection.inspector_note}
        </div>

        <div style={{ marginTop: 10, fontSize: '0.62rem', color: 'var(--text-muted)' }}>
          <div>Confidence: {(inspection.confidence * 100).toFixed(1)}%</div>
          <div>VLM: {inspection.vlm_provider} / {inspection.vlm_model}</div>
          {inspection.processing_time_ms && <div>Processed in {inspection.processing_time_ms}ms</div>}
        </div>
      </div>
    </div>
  )
}
