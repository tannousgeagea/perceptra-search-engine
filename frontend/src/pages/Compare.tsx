import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layers, Eye, EyeOff, ZoomIn, ZoomOut, RotateCcw, Columns2 } from 'lucide-react'
import { useCompare } from '../context/CompareContext'

export default function Compare() {
  const { items, clearAll } = useCompare()
  const navigate = useNavigate()
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [overlayMode, setOverlayMode] = useState(false)
  const [overlayOpacity, setOverlayOpacity] = useState(50)
  const [showDetections, setShowDetections] = useState(true)
  const isDragging = useRef(false)
  const lastPos = useRef({ x: 0, y: 0 })

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    setZoom((z) => Math.max(0.5, Math.min(5, z + (e.deltaY > 0 ? -0.1 : 0.1))))
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    isDragging.current = true
    lastPos.current = { x: e.clientX, y: e.clientY }
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging.current) return
    const dx = e.clientX - lastPos.current.x
    const dy = e.clientY - lastPos.current.y
    lastPos.current = { x: e.clientX, y: e.clientY }
    setPan((p) => ({ x: p.x + dx, y: p.y + dy }))
  }, [])

  const handleMouseUp = useCallback(() => {
    isDragging.current = false
  }, [])

  const resetView = () => { setZoom(1); setPan({ x: 0, y: 0 }) }

  if (items.length === 0) {
    return (
      <div className="page-container">
        <div className="empty-state">
          <div className="empty-state-icon"><Columns2 size={32} /></div>
          <p>No items to compare</p>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
            Add 2-4 images or detections from Search, Media Library, or detail pages
          </p>
          <button className="btn btn-primary btn-sm" onClick={() => navigate('/media')}>
            Go to Media Library
          </button>
        </div>
      </div>
    )
  }

  const gridCols = overlayMode ? 1 : items.length <= 2 ? 2 : 2

  return (
    <div className="page-container" style={{ height: 'calc(100vh - 60px)', display: 'flex', flexDirection: 'column' }}>
      {/* Header + Controls */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 0', marginBottom: 8, flexShrink: 0,
      }}>
        <div>
          <h1 className="page-title" style={{ marginBottom: 2 }}>Compare</h1>
          <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{items.length} items — Scroll to zoom, drag to pan</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setZoom((z) => Math.min(5, z + 0.25))} title="Zoom in">
            <ZoomIn size={14} />
          </button>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', minWidth: 40, textAlign: 'center' }}>
            {Math.round(zoom * 100)}%
          </span>
          <button className="btn btn-ghost btn-sm" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} title="Zoom out">
            <ZoomOut size={14} />
          </button>
          <button className="btn btn-ghost btn-sm" onClick={resetView} title="Reset view">
            <RotateCcw size={14} />
          </button>

          <div style={{ width: 1, height: 20, background: 'var(--border-base)' }} />

          {items.length >= 2 && (
            <button
              className={`btn btn-sm ${overlayMode ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setOverlayMode(!overlayMode)}
              title="Overlay mode"
            >
              <Layers size={14} /> Overlay
            </button>
          )}

          {overlayMode && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>Opacity</span>
              <input
                type="range" min="0" max="100" value={overlayOpacity}
                onChange={(e) => setOverlayOpacity(Number(e.target.value))}
                style={{ width: 80 }}
              />
              <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', width: 30 }}>
                {overlayOpacity}%
              </span>
            </div>
          )}

          <button
            className={`btn btn-sm ${showDetections ? 'btn-secondary' : 'btn-ghost'}`}
            onClick={() => setShowDetections(!showDetections)}
            title="Toggle detection overlays"
          >
            {showDetections ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>

          <div style={{ width: 1, height: 20, background: 'var(--border-base)' }} />

          <button className="btn btn-ghost btn-sm" onClick={() => { clearAll(); navigate('/media') }}>
            Done
          </button>
        </div>
      </div>

      {/* Comparison grid */}
      {overlayMode ? (
        /* Overlay mode: stack first two images */
        <div
          style={{
            flex: 1, position: 'relative', overflow: 'hidden',
            background: 'var(--bg-void)', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-dim)',
            cursor: isDragging.current ? 'grabbing' : 'grab',
          }}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          {items.slice(0, 2).map((item, i) => (
            <div
              key={`${item.type}-${item.id}`}
              style={{
                position: i === 0 ? 'relative' : 'absolute',
                top: 0, left: 0, width: '100%', height: i === 0 ? '100%' : 'auto',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                opacity: i === 0 ? 1 : overlayOpacity / 100,
                transition: 'opacity 0.15s ease',
              }}
            >
              <img
                src={item.url}
                alt={item.label}
                style={{
                  transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
                  maxWidth: '100%',
                  maxHeight: '100%',
                  objectFit: 'contain',
                  userSelect: 'none',
                  pointerEvents: 'none',
                }}
                draggable={false}
              />
            </div>
          ))}
          {/* Overlay label */}
          <div style={{
            position: 'absolute', bottom: 12, left: 12,
            display: 'flex', gap: 8,
          }}>
            {items.slice(0, 2).map((item, i) => (
              <span key={i} className={`badge ${i === 0 ? 'badge-amber' : 'badge-cyan'}`} style={{ fontSize: 10 }}>
                {item.label || item.type}
              </span>
            ))}
          </div>
        </div>
      ) : (
        /* Grid mode: side by side */
        <div
          style={{
            flex: 1,
            display: 'grid',
            gridTemplateColumns: `repeat(${gridCols}, 1fr)`,
            gap: 8,
            overflow: 'hidden',
          }}
        >
          {items.map((item) => (
            <div
              key={`${item.type}-${item.id}`}
              style={{
                position: 'relative',
                overflow: 'hidden',
                background: 'var(--bg-void)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-dim)',
                display: 'flex',
                flexDirection: 'column',
                cursor: isDragging.current ? 'grabbing' : 'grab',
              }}
              onWheel={handleWheel}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            >
              {/* Image */}
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                <img
                  src={item.url}
                  alt={item.label}
                  style={{
                    transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
                    maxWidth: '100%',
                    maxHeight: '100%',
                    objectFit: 'contain',
                    userSelect: 'none',
                    pointerEvents: 'none',
                  }}
                  draggable={false}
                />
              </div>

              {/* Metadata */}
              <div style={{
                padding: '8px 12px',
                borderTop: '1px solid var(--border-dim)',
                background: 'var(--bg-surface)',
                display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
                flexShrink: 0,
              }}>
                {item.label && <span className="badge badge-amber" style={{ fontSize: 10 }}>{item.label}</span>}
                <span className="badge badge-muted" style={{ fontSize: 10 }}>{item.type}</span>
                {item.plant_site && (
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{item.plant_site}</span>
                )}
                {item.captured_at && (
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                    {new Date(item.captured_at).toLocaleDateString()}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
