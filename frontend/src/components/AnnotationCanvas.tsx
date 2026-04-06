import { useRef, useState, useEffect, useCallback } from 'react'
import {
  Plus, Trash2, Check, X, Tag, MousePointer, Square,
  AlertCircle, Loader2, Save,
} from 'lucide-react'
import { createDetection } from '../api/client'
import type { DetectionCreateRequest } from '../types/api'

/* ─── Types ───────────────────────────────────────────────── */

interface BBox {
  /** All values normalised 0-1 */
  x: number
  y: number
  w: number
  h: number
}

interface PendingDetection {
  id: string          // client-side temp id
  bbox: BBox
  label: string
  confidence: number
}

interface AnnotationCanvasProps {
  imageUrl: string
  imageId: number
  imageWidth: number
  imageHeight: number
  onDone: () => void   // called after save — parent should refresh detections
  onCancel: () => void
}

/* ─── Helpers ─────────────────────────────────────────────── */

const LABEL_PRESETS = [
  'metallic pipe', 'rust', 'corrosion', 'container', 'crack',
  'deformation', 'foreign object', 'leak', 'discoloration', 'other',
]

const BOX_COLORS = [
  '#EF4444', '#F59E0B', '#10B981', '#6366F1', '#EC4899',
  '#22D3EE', '#8B5CF6', '#F97316', '#14B8A6', '#E11D48',
]

function clamp(v: number, min: number, max: number) { return Math.max(min, Math.min(max, v)) }

/* ─── Component ───────────────────────────────────────────── */

export default function AnnotationCanvas({
  imageUrl, imageId, imageWidth, imageHeight, onDone, onCancel,
}: AnnotationCanvasProps) {

  const containerRef = useRef<HTMLDivElement>(null)
  const [imgLoaded, setImgLoaded] = useState(false)
  const [displaySize, setDisplaySize] = useState({ w: 0, h: 0 })

  // Drawing state
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null)
  const [drawCurrent, setDrawCurrent] = useState<{ x: number; y: number } | null>(null)

  // Detections
  const [detections, setDetections] = useState<PendingDetection[]>([])
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)

  // Label form
  const [showLabelForm, setShowLabelForm] = useState(false)
  const [pendingBbox, setPendingBbox] = useState<BBox | null>(null)
  const [labelInput, setLabelInput] = useState('')
  const [confInput, setConfInput] = useState('1.0')

  // Save state
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [savedCount, setSavedCount] = useState(0)

  // Track image display size for coordinate conversion
  const updateDisplaySize = useCallback(() => {
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    setDisplaySize({ w: rect.width, h: rect.height })
  }, [])

  useEffect(() => {
    updateDisplaySize()
    window.addEventListener('resize', updateDisplaySize)
    return () => window.removeEventListener('resize', updateDisplaySize)
  }, [updateDisplaySize, imgLoaded])

  /* ── Coordinate conversion (display pixels → normalised 0-1) ── */
  const pxToNorm = useCallback((px: number, py: number): { nx: number; ny: number } => {
    if (displaySize.w === 0 || displaySize.h === 0) return { nx: 0, ny: 0 }
    return {
      nx: clamp(px / displaySize.w, 0, 1),
      ny: clamp(py / displaySize.h, 0, 1),
    }
  }, [displaySize])

  /* ── Mouse handlers for drawing ── */
  const handleMouseDown = (e: React.MouseEvent) => {
    if (showLabelForm) return
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setIsDrawing(true)
    setDrawStart({ x, y })
    setDrawCurrent({ x, y })
    setSelectedIdx(null)
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDrawing || !containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    setDrawCurrent({
      x: clamp(e.clientX - rect.left, 0, rect.width),
      y: clamp(e.clientY - rect.top, 0, rect.height),
    })
  }

  const handleMouseUp = () => {
    if (!isDrawing || !drawStart || !drawCurrent) {
      setIsDrawing(false)
      return
    }
    setIsDrawing(false)

    // Compute normalised bbox
    const { nx: x1, ny: y1 } = pxToNorm(drawStart.x, drawStart.y)
    const { nx: x2, ny: y2 } = pxToNorm(drawCurrent.x, drawCurrent.y)
    const bx = Math.min(x1, x2)
    const by = Math.min(y1, y2)
    const bw = Math.abs(x2 - x1)
    const bh = Math.abs(y2 - y1)

    // Ignore tiny accidental clicks
    if (bw < 0.01 || bh < 0.01) {
      setDrawStart(null)
      setDrawCurrent(null)
      return
    }

    // Show label form
    setPendingBbox({ x: bx, y: by, w: bw, h: bh })
    setLabelInput('')
    setConfInput('1.0')
    setShowLabelForm(true)
    setDrawStart(null)
    setDrawCurrent(null)
  }

  /* ── Label form handlers ── */
  const confirmDetection = () => {
    if (!pendingBbox || !labelInput.trim()) return
    const conf = parseFloat(confInput)
    if (isNaN(conf) || conf < 0 || conf > 1) return

    setDetections(prev => [...prev, {
      id: crypto.randomUUID(),
      bbox: pendingBbox,
      label: labelInput.trim(),
      confidence: conf,
    }])
    setPendingBbox(null)
    setShowLabelForm(false)
  }

  const cancelDetection = () => {
    setPendingBbox(null)
    setShowLabelForm(false)
  }

  const removeDetection = (idx: number) => {
    setDetections(prev => prev.filter((_, i) => i !== idx))
    if (selectedIdx === idx) setSelectedIdx(null)
  }

  /* ── Save all detections ── */
  const handleSaveAll = async () => {
    if (detections.length === 0) return
    setSaving(true)
    setSaveError('')
    setSavedCount(0)

    let successCount = 0
    for (const det of detections) {
      try {
        const req: DetectionCreateRequest = {
          image_id: imageId,
          bbox_x: det.bbox.x,
          bbox_y: det.bbox.y,
          bbox_width: det.bbox.w,
          bbox_height: det.bbox.h,
          bbox_format: 'normalized',
          label: det.label,
          confidence: det.confidence,
        }
        await createDetection(req)
        successCount++
        setSavedCount(successCount)
      } catch {
        setSaveError(`Failed at detection ${successCount + 1} of ${detections.length}`)
        break
      }
    }

    setSaving(false)
    if (successCount === detections.length) {
      onDone()
    }
  }

  /* ── Drawing preview rectangle (while dragging) ── */
  const drawRect = drawStart && drawCurrent ? {
    left: Math.min(drawStart.x, drawCurrent.x),
    top: Math.min(drawStart.y, drawCurrent.y),
    width: Math.abs(drawCurrent.x - drawStart.x),
    height: Math.abs(drawCurrent.y - drawStart.y),
  } : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px',
        background: 'var(--bg-elevated)', border: '1px solid var(--border-bright)',
        borderRadius: 'var(--radius-md)',
      }}>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Square size={14} style={{ color: 'var(--amber)' }} />
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
              Draw Mode
            </span>
          </div>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {detections.length} detection{detections.length !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn btn-ghost btn-sm" onClick={onCancel} disabled={saving}>
            <X size={12} /> Cancel
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSaveAll}
            disabled={saving || detections.length === 0}
          >
            {saving ? (
              <><Loader2 size={12} style={{ animation: 'spin 0.8s linear infinite' }} /> Saving {savedCount}/{detections.length}...</>
            ) : (
              <><Save size={12} /> Save {detections.length} Detection{detections.length !== 1 ? 's' : ''}</>
            )}
          </button>
        </div>
      </div>

      {saveError && (
        <div className="alert alert-error">
          <AlertCircle size={14} />
          <span>{saveError}</span>
        </div>
      )}

      {/* Instruction hint */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 12px',
        background: 'linear-gradient(135deg, rgba(245,166,35,0.06), rgba(34,211,238,0.04))',
        border: '1px solid var(--border-amber)',
        borderRadius: 'var(--radius-md)',
        fontSize: 12, color: 'var(--text-secondary)',
      }}>
        <MousePointer size={14} style={{ color: 'var(--amber)', flexShrink: 0 }} />
        Click and drag on the image to draw a bounding box. Release to set a label.
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16, alignItems: 'start' }}>
        {/* Canvas area */}
        <div style={{ position: 'relative', borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '2px solid var(--border-bright)', background: '#000' }}>
          <div
            ref={containerRef}
            style={{ position: 'relative', cursor: showLabelForm ? 'default' : 'crosshair', userSelect: 'none' }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={() => { if (isDrawing) handleMouseUp() }}
          >
            <img
              src={imageUrl}
              alt="Annotate"
              style={{ width: '100%', height: 'auto', display: 'block', pointerEvents: 'none' }}
              onLoad={() => setImgLoaded(true)}
              draggable={false}
            />

            {/* Existing detection overlays */}
            {detections.map((det, i) => (
              <div
                key={det.id}
                onClick={(e) => { e.stopPropagation(); setSelectedIdx(i) }}
                style={{
                  position: 'absolute',
                  left: `${det.bbox.x * 100}%`,
                  top: `${det.bbox.y * 100}%`,
                  width: `${det.bbox.w * 100}%`,
                  height: `${det.bbox.h * 100}%`,
                  border: `2px solid ${BOX_COLORS[i % BOX_COLORS.length]}`,
                  borderRadius: 2,
                  cursor: 'pointer',
                  boxShadow: selectedIdx === i ? `0 0 0 2px ${BOX_COLORS[i % BOX_COLORS.length]}44, 0 0 12px ${BOX_COLORS[i % BOX_COLORS.length]}33` : 'none',
                  background: selectedIdx === i ? `${BOX_COLORS[i % BOX_COLORS.length]}10` : 'transparent',
                  transition: 'box-shadow 0.15s, background 0.15s',
                  pointerEvents: showLabelForm ? 'none' : 'auto',
                }}
              >
                {/* Label tag */}
                <div style={{
                  position: 'absolute', top: -1, left: -1,
                  padding: '1px 6px',
                  background: BOX_COLORS[i % BOX_COLORS.length],
                  borderRadius: '2px 0 4px 0',
                  fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 700,
                  color: '#fff', whiteSpace: 'nowrap',
                  pointerEvents: 'none',
                }}>
                  {det.label} {Math.round(det.confidence * 100)}%
                </div>
              </div>
            ))}

            {/* Drawing preview rect */}
            {drawRect && (
              <div style={{
                position: 'absolute',
                left: drawRect.left, top: drawRect.top,
                width: drawRect.width, height: drawRect.height,
                border: '2px dashed var(--amber)',
                borderRadius: 2,
                background: 'rgba(245,166,35,0.08)',
                pointerEvents: 'none',
              }} />
            )}

            {/* Pending bbox (label form open) */}
            {pendingBbox && (
              <div style={{
                position: 'absolute',
                left: `${pendingBbox.x * 100}%`,
                top: `${pendingBbox.y * 100}%`,
                width: `${pendingBbox.w * 100}%`,
                height: `${pendingBbox.h * 100}%`,
                border: '2px solid var(--amber)',
                borderRadius: 2,
                background: 'rgba(245,166,35,0.12)',
                pointerEvents: 'none',
                animation: 'pulse 1.5s ease-in-out infinite',
              }} />
            )}
          </div>

          {/* Label form overlay */}
          {showLabelForm && pendingBbox && (
            <div style={{
              position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
              width: 320, padding: 16,
              background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
              borderRadius: 'var(--radius-lg)',
              boxShadow: 'var(--shadow-lg)',
              animation: 'fadeUp 0.2s ease-out',
              zIndex: 10,
            }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, letterSpacing: '0.04em', color: 'var(--text-primary)', marginBottom: 12 }}>
                Label This Detection
              </div>

              <div className="form-group" style={{ marginBottom: 10 }}>
                <label className="form-label">Label <span style={{ color: 'var(--danger)' }}>*</span></label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. crack, rust, foreign object"
                  value={labelInput}
                  onChange={e => setLabelInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && labelInput.trim()) confirmDetection() }}
                  autoFocus
                />
              </div>

              {/* Quick label presets */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 10 }}>
                {LABEL_PRESETS.map(preset => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setLabelInput(preset)}
                    style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 10,
                      fontFamily: 'var(--font-mono)', cursor: 'pointer',
                      border: labelInput === preset ? '1px solid var(--amber)' : '1px solid var(--border-dim)',
                      background: labelInput === preset ? 'var(--amber-glow)' : 'transparent',
                      color: labelInput === preset ? 'var(--amber)' : 'var(--text-muted)',
                      transition: 'all 0.1s',
                    }}
                  >
                    {preset}
                  </button>
                ))}
              </div>

              <div className="form-group" style={{ marginBottom: 12 }}>
                <label className="form-label">Confidence</label>
                <input
                  type="range"
                  min="0" max="1" step="0.05"
                  value={confInput}
                  onChange={e => setConfInput(e.target.value)}
                  style={{ width: '100%', accentColor: 'var(--amber)' }}
                />
                <div className="flex justify-between" style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginTop: 2 }}>
                  <span>0%</span>
                  <span style={{ color: 'var(--amber)', fontWeight: 700, fontSize: 12 }}>{Math.round(parseFloat(confInput) * 100)}%</span>
                  <span>100%</span>
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <button className="btn btn-ghost btn-sm" onClick={cancelDetection}>
                  <X size={11} /> Discard
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={confirmDetection}
                  disabled={!labelInput.trim()}
                >
                  <Plus size={11} /> Add Detection
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Detection list sidebar */}
        <div style={{
          background: 'var(--bg-surface)', border: '1px solid var(--border-base)',
          borderRadius: 'var(--radius-md)', overflow: 'hidden',
        }}>
          <div style={{
            padding: '10px 14px', borderBottom: '1px solid var(--border-dim)',
            fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600,
            letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-secondary)',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Tag size={12} />
            Detections ({detections.length})
          </div>

          {detections.length === 0 ? (
            <div style={{ padding: '32px 16px', textAlign: 'center' }}>
              <Square size={20} style={{ color: 'var(--text-muted)', margin: '0 auto 8px' }} />
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Draw a box on the image to start annotating
              </p>
            </div>
          ) : (
            <div style={{ maxHeight: 400, overflowY: 'auto' }}>
              {detections.map((det, i) => (
                <div
                  key={det.id}
                  onClick={() => setSelectedIdx(i)}
                  style={{
                    padding: '10px 14px',
                    borderBottom: '1px solid var(--border-dim)',
                    cursor: 'pointer',
                    background: selectedIdx === i ? 'var(--bg-elevated)' : 'transparent',
                    transition: 'background 0.1s',
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div style={{
                        width: 10, height: 10, borderRadius: 2, flexShrink: 0,
                        background: BOX_COLORS[i % BOX_COLORS.length],
                      }} />
                      <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                        {det.label}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span style={{
                        fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
                        color: det.confidence >= 0.8 ? 'var(--success)' : 'var(--amber)',
                      }}>
                        {Math.round(det.confidence * 100)}%
                      </span>
                      <button
                        className="btn btn-ghost btn-icon"
                        style={{ padding: 2 }}
                        onClick={(e) => { e.stopPropagation(); removeDetection(i) }}
                        title="Remove"
                      >
                        <Trash2 size={11} style={{ color: 'var(--danger)' }} />
                      </button>
                    </div>
                  </div>
                  <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginTop: 3 }}>
                    {(det.bbox.x * imageWidth).toFixed(0)},{(det.bbox.y * imageHeight).toFixed(0)} {(det.bbox.w * imageWidth).toFixed(0)}x{(det.bbox.h * imageHeight).toFixed(0)}px
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
