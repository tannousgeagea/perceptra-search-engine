import { useEffect, useState } from 'react'
import type { WasteCamera, WasteInspection, WasteComposition } from '../../types/api'
import { getWasteCameraTrend } from '../../api/client'
import { useCameraStream } from './hooks/useCameraStream'

const MATERIALS = ['plastic', 'paper', 'glass', 'metal', 'organic', 'e_waste', 'hazardous', 'other'] as const
type Material = typeof MATERIALS[number]

const COLOR_MAP: Record<Material, string> = {
  plastic:  '#0ea5e9',
  paper:    '#a3e635',
  glass:    '#38bdf8',
  metal:    '#94a3b8',
  organic:  '#86efac',
  e_waste:  '#f97316',
  hazardous:'#ef4444',
  other:    '#64748b',
}

function CompositionBars({ comp }: { comp: WasteComposition }) {
  return (
    <div>
      {MATERIALS.map(mat => {
        const val = comp[mat] ?? 0
        const isHigh = mat === 'hazardous' && val > 10
        return (
          <div key={mat} className="wv-comp-bar-row">
            <span className="wv-comp-label" style={{ color: isHigh ? 'var(--wv-red)' : undefined }}>
              {mat.replace('_', '-')}
            </span>
            <div className="wv-comp-track">
              <div
                className="wv-comp-fill"
                style={{ width: `${val}%`, background: isHigh ? 'var(--wv-red)' : COLOR_MAP[mat] }}
              />
            </div>
            <span className="wv-comp-pct" style={{ color: isHigh ? 'var(--wv-red)' : undefined }}>
              {Math.round(val)}%
            </span>
          </div>
        )
      })}
    </div>
  )
}

function TrendSparkline({
  history,
  material,
}: {
  history: WasteInspection[]
  material: Material
}) {
  if (history.length < 2) return null
  const values = history.map(h => h.waste_composition[material] ?? 0)
  const max = Math.max(...values, 1)
  const W = 300
  const H = 60
  const pts = values
    .map((v, i) => `${(i / (values.length - 1)) * W},${H - (v / max) * H}`)
    .join(' ')

  return (
    <svg width={W} height={H} style={{ overflow: 'visible' }}>
      <polyline
        points={pts}
        fill="none"
        stroke={COLOR_MAP[material]}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.8}
      />
    </svg>
  )
}

export default function CompositionPanel({ cameras }: { cameras: WasteCamera[] }) {
  const [selectedCamUuid, setSelectedCamUuid] = useState<string | null>(cameras[0]?.camera_uuid ?? null)
  const [trendMaterial, setTrendMaterial] = useState<Material>('plastic')
  const [history, setHistory] = useState<WasteInspection[]>([])

  const { latestInspection } = useCameraStream(selectedCamUuid)

  useEffect(() => {
    if (cameras.length > 0 && !selectedCamUuid) {
      setSelectedCamUuid(cameras[0].camera_uuid)
    }
  }, [cameras])

  useEffect(() => {
    if (!selectedCamUuid) return
    getWasteCameraTrend(selectedCamUuid, 60).then(r => setHistory(r.data)).catch(() => {})
  }, [selectedCamUuid])

  // Prepend live updates to history
  useEffect(() => {
    if (!latestInspection) return
    setHistory(prev => {
      const without = prev.filter(h => h.inspection_uuid !== latestInspection.inspection_uuid)
      return [...without, latestInspection].slice(-60)
    })
  }, [latestInspection])

  const currentComp = latestInspection?.waste_composition ?? history[history.length - 1]?.waste_composition

  return (
    <div style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      {/* Camera selector */}
      <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 12 }}>
        <label style={{ fontSize: '0.65rem', color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          Camera
        </label>
        <select
          className="wv-select"
          value={selectedCamUuid ?? ''}
          onChange={e => setSelectedCamUuid(e.target.value)}
        >
          {cameras.map(c => (
            <option key={c.camera_uuid} value={c.camera_uuid}>{c.name} — {c.location}</option>
          ))}
        </select>
        {latestInspection && (
          <span className={`wv-risk-badge ${latestInspection.overall_risk}`}>
            {latestInspection.overall_risk.toUpperCase()}
          </span>
        )}
      </div>

      {/* Current composition bars */}
      <div className="wv-panel">
        <div className="wv-panel-header">
          <span>Current Composition</span>
          {latestInspection && (
            <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>
              Live · conf {(latestInspection.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
        <div style={{ padding: '14px 16px' }}>
          {currentComp ? (
            <CompositionBars comp={currentComp} />
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', padding: '12px 0' }}>
              No data yet — waiting for first inspection...
            </div>
          )}
        </div>
      </div>

      {/* Trend chart */}
      <div className="wv-panel">
        <div className="wv-panel-header">
          <span>Trend — Last {history.length} Inspections</span>
          <select
            className="wv-select"
            style={{ fontSize: '0.62rem', padding: '2px 6px' }}
            value={trendMaterial}
            onChange={e => setTrendMaterial(e.target.value as Material)}
          >
            {MATERIALS.map(m => <option key={m} value={m}>{m.replace('_', '-')}</option>)}
          </select>
        </div>
        <div style={{ padding: '14px 16px' }}>
          {history.length < 2 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>
              Collecting data...
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <TrendSparkline history={history} material={trendMaterial} />
              <div style={{
                display: 'flex', justifyContent: 'space-between',
                fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: 4,
              }}>
                <span>{new Date(history[0]?.created_at).toLocaleTimeString()}</span>
                <span style={{ color: COLOR_MAP[trendMaterial], fontWeight: 600 }}>
                  {trendMaterial.replace('_', '-').toUpperCase()}
                </span>
                <span>{new Date(history[history.length - 1]?.created_at).toLocaleTimeString()}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Inspector note */}
      {latestInspection?.inspector_note && (
        <div style={{ gridColumn: '1 / -1' }}>
          <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>
            Inspector Note
          </div>
          <div className="wv-inspector-note">{latestInspection.inspector_note}</div>
        </div>
      )}
    </div>
  )
}
