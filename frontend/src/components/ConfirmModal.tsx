import { useEffect } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'

interface ConfirmModalProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  confirmVariant?: 'danger' | 'primary'
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmModal({
  open, title, description,
  confirmLabel = 'Confirm',
  confirmVariant = 'danger',
  loading = false,
  onConfirm, onCancel,
}: ConfirmModalProps) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onCancel()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, loading, onCancel])

  if (!open) return null

  return (
    <div
      className="modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget && !loading) onCancel() }}
    >
      <div className="modal" style={{ maxWidth: 420 }}>
        <div style={{
          textAlign: 'center', marginBottom: 20,
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%',
            background: confirmVariant === 'danger' ? 'var(--danger-dim)' : 'var(--amber-glow)',
            border: `1px solid ${confirmVariant === 'danger' ? 'rgba(239,68,68,0.3)' : 'var(--border-amber)'}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <AlertCircle size={22} style={{ color: confirmVariant === 'danger' ? 'var(--danger)' : 'var(--amber)' }} />
          </div>
          <div>
            <div className="modal-title" style={{ marginBottom: 4 }}>{title}</div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {description}
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <button className="btn btn-ghost" onClick={onCancel} disabled={loading}>
            Cancel
          </button>
          <button
            className={`btn ${confirmVariant === 'danger' ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? (
              <><Loader2 size={13} style={{ animation: 'spin 0.8s linear infinite' }} /> Processing...</>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
