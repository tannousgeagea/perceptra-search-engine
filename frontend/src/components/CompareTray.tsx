import { useNavigate, useLocation } from 'react-router-dom'
import { X, Columns2 } from 'lucide-react'
import { useCompare } from '../context/CompareContext'

export default function CompareTray() {
  const { items, removeItem, clearAll } = useCompare()
  const navigate = useNavigate()
  const { pathname } = useLocation()

  // Don't show on compare page or when empty
  if (pathname === '/compare' || items.length === 0) return null

  return (
    <div style={{
      position: 'fixed',
      bottom: 20,
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 900,
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border-bright)',
      borderRadius: 'var(--radius-lg)',
      padding: '10px 16px',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      backdropFilter: 'blur(12px)',
      boxShadow: 'var(--shadow-lg)',
      animation: 'fadeUp 0.2s ease-out',
    }}>
      {/* Thumbnails */}
      <div style={{ display: 'flex', gap: 6 }}>
        {items.map((item) => (
          <div key={`${item.type}-${item.id}`} style={{ position: 'relative' }}>
            <div style={{
              width: 40, height: 30, borderRadius: 'var(--radius-sm)',
              overflow: 'hidden', background: 'var(--bg-muted)',
              border: '1px solid var(--border-dim)',
            }}>
              {item.url ? (
                <img src={item.url} alt={item.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: 'var(--text-muted)' }}>
                  {item.type === 'image' ? 'IMG' : 'DET'}
                </div>
              )}
            </div>
            <button
              onClick={() => removeItem(item.id)}
              style={{
                position: 'absolute', top: -4, right: -4,
                width: 14, height: 14, borderRadius: '50%',
                background: 'var(--danger)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', fontSize: 8, border: 'none',
              }}
            >
              <X size={8} />
            </button>
          </div>
        ))}
      </div>

      {/* Count */}
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)',
      }}>
        {items.length}/4
      </span>

      {/* Divider */}
      <div style={{ width: 1, height: 20, background: 'var(--border-base)' }} />

      {/* Compare button */}
      <button
        className="btn btn-primary btn-sm"
        onClick={() => navigate('/compare')}
        disabled={items.length < 2}
        style={{ fontSize: 12 }}
      >
        <Columns2 size={13} /> Compare
      </button>

      {/* Clear */}
      <button
        className="btn btn-ghost btn-sm"
        onClick={clearAll}
        style={{ fontSize: 11, color: 'var(--text-muted)' }}
      >
        Clear
      </button>
    </div>
  )
}
