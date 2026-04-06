import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, Check, CheckCheck, AlertTriangle, AlertCircle, Info } from 'lucide-react'
import type { AlertResponse } from '../types/api'
import { getAlerts, acknowledgeAlert, acknowledgeAllAlerts } from '../api/client'
import { useAlerts } from '../context/AlertContext'

interface AlertPanelProps {
  open: boolean
  onClose: () => void
}

const SEVERITY_CONFIG: Record<string, { icon: typeof AlertTriangle; color: string; bg: string }> = {
  critical: { icon: AlertTriangle, color: 'var(--danger)', bg: 'var(--danger-dim)' },
  warning: { icon: AlertCircle, color: 'var(--warning)', bg: 'var(--warning-dim)' },
  info: { icon: Info, color: 'var(--info)', bg: 'var(--info-dim)' },
}

export default function AlertPanel({ open, onClose }: AlertPanelProps) {
  const navigate = useNavigate()
  const { refreshUnreadCount } = useAlerts()
  const [alerts, setAlerts] = useState<AlertResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [ackingId, setAckingId] = useState<number | null>(null)
  const [ackingAll, setAckingAll] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    getAlerts({ page_size: 20, is_acknowledged: false })
      .then((r) => setAlerts(r.data.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [open])

  const handleAcknowledge = async (id: number) => {
    setAckingId(id)
    try {
      await acknowledgeAlert(id)
      setAlerts((prev) => prev.filter((a) => a.id !== id))
      refreshUnreadCount()
    } catch { /* ignore */ }
    setAckingId(null)
  }

  const handleAcknowledgeAll = async () => {
    setAckingAll(true)
    try {
      await acknowledgeAllAlerts()
      setAlerts([])
      refreshUnreadCount()
    } catch { /* ignore */ }
    setAckingAll(false)
  }

  const handleClickAlert = (alert: AlertResponse) => {
    onClose()
    navigate(`/media/detections/${alert.detection_id}`)
  }

  const formatTime = (dateStr: string) => {
    const d = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return 'just now'
    if (diffMin < 60) return `${diffMin}m ago`
    const diffHr = Math.floor(diffMin / 60)
    if (diffHr < 24) return `${diffHr}h ago`
    return `${Math.floor(diffHr / 24)}d ago`
  }

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          zIndex: 999, backdropFilter: 'blur(2px)',
        }}
      />

      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 400, maxWidth: '90vw',
        background: 'var(--bg-surface)', borderLeft: '1px solid var(--border-base)',
        zIndex: 1000, display: 'flex', flexDirection: 'column',
        animation: 'fadeLeft 0.2s ease-out',
        boxShadow: 'var(--shadow-lg)',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--border-dim)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertTriangle size={16} style={{ color: 'var(--amber)' }} />
            <span style={{
              fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 700,
              letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-primary)',
            }}>
              Active Alerts
            </span>
            {alerts.length > 0 && (
              <span className="badge badge-danger" style={{ fontSize: 10 }}>{alerts.length}</span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {alerts.length > 0 && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={handleAcknowledgeAll}
                disabled={ackingAll}
                style={{ fontSize: 11 }}
              >
                <CheckCheck size={13} />
                {ackingAll ? 'Clearing...' : 'Ack All'}
              </button>
            )}
            <button className="btn btn-ghost btn-icon" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Alert List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px' }}>
          {loading ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              Loading alerts...
            </div>
          ) : alerts.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              No active alerts
            </div>
          ) : (
            alerts.map((alert) => {
              const config = SEVERITY_CONFIG[alert.severity] ?? SEVERITY_CONFIG.info
              const SeverityIcon = config.icon
              return (
                <div
                  key={alert.id}
                  style={{
                    display: 'flex', gap: 10, padding: '10px 8px',
                    borderBottom: '1px solid var(--border-dim)',
                    cursor: 'pointer',
                    borderRadius: 'var(--radius-sm)',
                    transition: 'background var(--transition-fast)',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  {/* Crop thumbnail */}
                  <div
                    onClick={() => handleClickAlert(alert)}
                    style={{
                      width: 44, height: 44, borderRadius: 'var(--radius-sm)',
                      overflow: 'hidden', flexShrink: 0, background: 'var(--bg-muted)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    {alert.crop_url ? (
                      <img src={alert.crop_url} alt={alert.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <SeverityIcon size={18} style={{ color: config.color }} />
                    )}
                  </div>

                  {/* Content */}
                  <div onClick={() => handleClickAlert(alert)} style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                      <span className={`badge ${alert.severity === 'critical' ? 'badge-danger' : alert.severity === 'warning' ? 'badge-amber' : 'badge-muted'}`}
                        style={{ fontSize: 9 }}
                      >
                        {alert.severity.toUpperCase()}
                      </span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {alert.label}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 8 }}>
                      <span>{(alert.confidence * 100).toFixed(0)}%</span>
                      {alert.plant_site && <span>{alert.plant_site}</span>}
                      <span>{formatTime(alert.created_at)}</span>
                    </div>
                  </div>

                  {/* Acknowledge button */}
                  <button
                    className="btn btn-ghost btn-icon"
                    onClick={(e) => { e.stopPropagation(); handleAcknowledge(alert.id) }}
                    disabled={ackingId === alert.id}
                    title="Acknowledge"
                    style={{ flexShrink: 0, alignSelf: 'center' }}
                  >
                    <Check size={14} style={{ color: 'var(--success)' }} />
                  </button>
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 16px', borderTop: '1px solid var(--border-dim)',
          textAlign: 'center',
        }}>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => { onClose(); navigate('/alerts') }}
            style={{ fontSize: 12, width: '100%' }}
          >
            View All Alerts
          </button>
        </div>
      </div>
    </>
  )
}
