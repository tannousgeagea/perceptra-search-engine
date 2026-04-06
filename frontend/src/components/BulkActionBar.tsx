import { Trash2, Tag, Zap, X } from 'lucide-react'

interface BulkActionBarProps {
  count: number
  tab: 'images' | 'videos' | 'detections'
  onDelete: () => void
  onTag: () => void
  onRunDetection?: () => void
  onDeselectAll: () => void
}

export default function BulkActionBar({
  count, tab, onDelete, onTag, onRunDetection, onDeselectAll,
}: BulkActionBarProps) {
  return (
    <div style={{
      position: 'fixed',
      bottom: 24,
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 1000,
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '10px 20px',
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-bright)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: '0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.05)',
      animation: 'fadeUp 0.2s ease-out',
      backdropFilter: 'blur(12px)',
    }}>
      {/* Count badge */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '4px 12px',
        background: 'var(--amber-glow)',
        border: '1px solid var(--border-amber)',
        borderRadius: 'var(--radius-full)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        fontWeight: 700,
        color: 'var(--amber)',
        whiteSpace: 'nowrap',
      }}>
        {count} selected
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 24, background: 'var(--border-dim)' }} />

      {/* Actions */}
      <button className="btn btn-danger btn-sm" onClick={onDelete}>
        <Trash2 size={12} /> Delete
      </button>

      <button className="btn btn-secondary btn-sm" onClick={onTag}>
        <Tag size={12} /> Tag
      </button>

      {tab === 'images' && onRunDetection && (
        <button className="btn btn-secondary btn-sm" onClick={onRunDetection}>
          <Zap size={12} /> Detect
        </button>
      )}

      {/* Divider */}
      <div style={{ width: 1, height: 24, background: 'var(--border-dim)' }} />

      {/* Clear */}
      <button
        className="btn btn-ghost btn-icon btn-sm"
        onClick={onDeselectAll}
        title="Clear selection"
      >
        <X size={14} />
      </button>
    </div>
  )
}
