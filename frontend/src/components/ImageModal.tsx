import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut,
  Download, Maximize2, Minimize2, Info, ExternalLink,
} from 'lucide-react'

export interface ImageItem {
  url: string
  filename: string
  subtitle?: string          // e.g. "Detection · 87% confidence"
  badge?: string             // e.g. "DETECTION" or "IMAGE"
  badgeColor?: string        // css color
  meta?: Array<{ label: string; value: string | number }>
  detailUrl?: string         // e.g. "/media/images/42" — link to detail page
}

interface ImageModalProps {
  images: ImageItem[]
  initialIndex?: number
  onClose: () => void
}

export default function ImageModal({ images, initialIndex = 0, onClose }: ImageModalProps) {
  const navigate = useNavigate()
  const [index, setIndex] = useState(initialIndex)
  const [zoom, setZoom] = useState(false)
  const [infoOpen, setInfoOpen] = useState(false)

  const current = images[index]
  const hasPrev = index > 0
  const hasNext = index < images.length - 1

  const prev = useCallback(() => {
    if (hasPrev) { setIndex(i => i - 1); setZoom(false) }
  }, [hasPrev])

  const next = useCallback(() => {
    if (hasNext) { setIndex(i => i + 1); setZoom(false) }
  }, [hasNext])

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
      if (e.key === '+' || e.key === '=') setZoom(true)
      if (e.key === '-') setZoom(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, prev, next])

  // Lock body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  if (!current) return null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 2000,
        background: 'rgba(0,0,0,0.92)',
        backdropFilter: 'blur(6px)',
        display: 'flex', flexDirection: 'column',
        animation: 'fadeIn 0.15s ease-out',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 16px', flexShrink: 0,
        background: 'rgba(0,0,0,0.5)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
      }}>
        {/* Left: filename + badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          {current.badge && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600,
              letterSpacing: '0.08em', padding: '2px 7px', borderRadius: 3,
              background: current.badgeColor ? current.badgeColor + '22' : 'rgba(245,166,35,0.15)',
              color: current.badgeColor || 'var(--amber)',
              border: `1px solid ${(current.badgeColor || 'var(--amber)') + '44'}`,
              flexShrink: 0,
            }}>
              {current.badge}
            </span>
          )}
          <div style={{ minWidth: 0 }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14,
              color: '#E2E8F4', letterSpacing: '0.03em',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              maxWidth: '40vw',
            }}>
              {current.filename}
            </div>
            {current.subtitle && (
              <div style={{ fontSize: 11, color: 'rgba(139,151,181,0.9)', fontFamily: 'var(--font-mono)', marginTop: 1 }}>
                {current.subtitle}
              </div>
            )}
          </div>
        </div>

        {/* Right: counter + actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          {images.length > 1 && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 12, color: 'rgba(139,151,181,0.8)',
              padding: '4px 10px', background: 'rgba(255,255,255,0.05)',
              borderRadius: 4, border: '1px solid rgba(255,255,255,0.08)',
            }}>
              {index + 1} / {images.length}
            </span>
          )}
          {current.meta && current.meta.length > 0 && (
            <button
              onClick={() => setInfoOpen(o => !o)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 32, height: 32, borderRadius: 6, border: '1px solid rgba(255,255,255,0.1)',
                background: infoOpen ? 'rgba(245,166,35,0.15)' : 'rgba(255,255,255,0.05)',
                color: infoOpen ? '#F5A623' : 'rgba(139,151,181,0.9)',
                cursor: 'pointer',
              }}
              title="Toggle info"
            >
              <Info size={14} />
            </button>
          )}
          <button
            onClick={() => setZoom(z => !z)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 32, height: 32, borderRadius: 6, border: '1px solid rgba(255,255,255,0.1)',
              background: zoom ? 'rgba(245,166,35,0.15)' : 'rgba(255,255,255,0.05)',
              color: zoom ? '#F5A623' : 'rgba(139,151,181,0.9)',
              cursor: 'pointer',
            }}
            title={zoom ? 'Fit to screen (-)' : 'Zoom to actual size (+)'}
          >
            {zoom ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          {current.detailUrl && (
            <button
              onClick={() => { onClose(); navigate(current.detailUrl!) }}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                gap: 6, height: 32, borderRadius: 6, border: '1px solid rgba(245,166,35,0.3)',
                background: 'rgba(245,166,35,0.1)',
                color: '#F5A623',
                cursor: 'pointer',
                padding: '0 10px',
                fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 600,
                letterSpacing: '0.06em', textTransform: 'uppercase',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(245,166,35,0.2)' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(245,166,35,0.1)' }}
              title="View full details"
            >
              <ExternalLink size={12} />
              Details
            </button>
          )}
          {current.url && (
            <a
              href={current.url}
              download={current.filename}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 32, height: 32, borderRadius: 6, border: '1px solid rgba(255,255,255,0.1)',
                background: 'rgba(255,255,255,0.05)',
                color: 'rgba(139,151,181,0.9)',
                textDecoration: 'none',
                transition: 'all 0.15s',
              }}
              title="Download"
            >
              <Download size={14} />
            </a>
          )}
          <button
            onClick={onClose}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 32, height: 32, borderRadius: 6, border: '1px solid rgba(255,255,255,0.1)',
              background: 'rgba(255,255,255,0.05)',
              color: 'rgba(139,151,181,0.9)',
              cursor: 'pointer',
            }}
            title="Close (Esc)"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Main area: nav + image */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'stretch', minHeight: 0, position: 'relative' }}>

        {/* Prev arrow */}
        <button
          onClick={prev}
          disabled={!hasPrev}
          style={{
            position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)',
            zIndex: 10,
            width: 44, height: 44, borderRadius: '50%',
            background: hasPrev ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.12)',
            color: hasPrev ? '#E2E8F4' : 'rgba(255,255,255,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: hasPrev ? 'pointer' : 'default',
            transition: 'all 0.15s',
            backdropFilter: 'blur(4px)',
          }}
          onMouseEnter={(e) => hasPrev && ((e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.2)')}
          onMouseLeave={(e) => hasPrev && ((e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.1)')}
          title="Previous (←)"
        >
          <ChevronLeft size={20} />
        </button>

        {/* Image container */}
        <div
          onClick={() => setZoom(z => !z)}
          style={{
            flex: 1,
            overflow: zoom ? 'auto' : 'hidden',
            display: 'flex',
            alignItems: zoom ? 'flex-start' : 'center',
            justifyContent: zoom ? 'flex-start' : 'center',
            padding: zoom ? 16 : '16px 64px',
            cursor: zoom ? 'zoom-out' : 'zoom-in',
          }}
        >
          <img
            key={current.url}
            src={current.url}
            alt={current.filename}
            style={{
              maxWidth: zoom ? 'none' : '100%',
              maxHeight: zoom ? 'none' : '100%',
              width: zoom ? 'auto' : 'auto',
              height: zoom ? 'auto' : 'auto',
              objectFit: zoom ? 'none' : 'contain',
              borderRadius: 6,
              boxShadow: '0 8px 40px rgba(0,0,0,0.6)',
              display: 'block',
              animation: 'fadeIn 0.2s ease-out',
              userSelect: 'none',
            }}
            draggable={false}
          />
        </div>

        {/* Next arrow */}
        <button
          onClick={next}
          disabled={!hasNext}
          style={{
            position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
            zIndex: 10,
            width: 44, height: 44, borderRadius: '50%',
            background: hasNext ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.12)',
            color: hasNext ? '#E2E8F4' : 'rgba(255,255,255,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: hasNext ? 'pointer' : 'default',
            transition: 'all 0.15s',
            backdropFilter: 'blur(4px)',
          }}
          onMouseEnter={(e) => hasNext && ((e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.2)')}
          onMouseLeave={(e) => hasNext && ((e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.1)')}
          title="Next (→)"
        >
          <ChevronRight size={20} />
        </button>

        {/* Info panel (right side) */}
        {infoOpen && current.meta && (
          <div style={{
            width: 240, flexShrink: 0,
            background: 'rgba(10,12,20,0.85)',
            borderLeft: '1px solid rgba(255,255,255,0.08)',
            padding: 20,
            overflowY: 'auto',
            animation: 'fadeLeft 0.2s ease-out',
          }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 600,
              letterSpacing: '0.12em', textTransform: 'uppercase',
              color: 'rgba(139,151,181,0.7)', marginBottom: 14,
            }}>
              Metadata
            </div>
            {current.meta.map(({ label, value }) => (
              <div key={label} style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'rgba(139,151,181,0.55)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>
                  {label}
                </div>
                <div style={{ fontSize: 13, color: '#E2E8F4', fontWeight: 500, wordBreak: 'break-all' }}>
                  {value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom thumbnails strip (when >1 image) */}
      {images.length > 1 && (
        <div style={{
          flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 6, padding: '10px 16px',
          background: 'rgba(0,0,0,0.5)',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          overflowX: 'auto',
        }}>
          {images.map((img, i) => (
            <button
              key={i}
              onClick={() => { setIndex(i); setZoom(false) }}
              style={{
                width: 48, height: 36, flexShrink: 0,
                borderRadius: 4, overflow: 'hidden',
                border: `2px solid ${i === index ? '#F5A623' : 'rgba(255,255,255,0.1)'}`,
                padding: 0, cursor: 'pointer',
                opacity: i === index ? 1 : 0.55,
                transition: 'all 0.15s',
                background: 'rgba(255,255,255,0.05)',
              }}
            >
              <img
                src={img.url}
                alt={img.filename}
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
              />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
