import { useEffect, useState } from 'react'
import type { WasteAlert } from '../../types/api'
import { listWasteAlerts } from '../../api/client'
import { useWasteAlerts } from './hooks/useWasteAlerts'

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function AlertRow({ alert, onAck }: { alert: WasteAlert; onAck: () => void }) {
  const sev = alert.severity

  return (
    <div className={`wv-alert-row ${alert.is_acknowledged ? '' : `unread ${sev}`}`}>
      <span className="wv-alert-time">{formatTime(alert.created_at)}</span>
      <div className="wv-alert-body">
        <div className="wv-alert-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`wv-risk-badge ${sev}`}>{sev.toUpperCase()}</span>
          <span>{(alert.details as Record<string, unknown>)?.item as string || alert.alert_type.replace('_', ' ').toUpperCase()}</span>
        </div>
        <div className="wv-alert-camera">
          {alert.alert_type.toUpperCase()}
          {(alert.details as Record<string, unknown>)?.action
            ? ` · ${(alert.details as Record<string, unknown>).action}`
            : ''}
        </div>
      </div>
      {!alert.is_acknowledged && (
        <button className="wv-ack-btn" onClick={onAck}>ACK</button>
      )}
      {alert.is_acknowledged && (
        <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', flexShrink: 0 }}>✓ ACK</span>
      )}
    </div>
  )
}

export default function AlertFeed() {
  const { alerts: liveAlerts, unreadCount, connected, acknowledge } = useWasteAlerts()
  const [historicalAlerts, setHistoricalAlerts] = useState<WasteAlert[]>([])
  const [loadingHistory, setLoadingHistory] = useState(true)

  useEffect(() => {
    setLoadingHistory(true)
    listWasteAlerts({ page_size: 50 })
      .then(r => setHistoricalAlerts(r.data.items))
      .catch(() => {})
      .finally(() => setLoadingHistory(false))
  }, [])

  // Merge live + historical, deduplicated by alert_uuid
  const seen = new Set<string>()
  const merged: WasteAlert[] = []
  for (const a of [...liveAlerts, ...historicalAlerts]) {
    if (!seen.has(a.alert_uuid)) {
      seen.add(a.alert_uuid)
      merged.push(a)
    }
  }
  merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 16px', borderBottom: '1px solid var(--wv-border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Alert Feed
          </span>
          {unreadCount > 0 && (
            <span style={{
              background: 'var(--wv-red)', color: '#fff',
              fontSize: '0.6rem', fontWeight: 700,
              padding: '1px 7px', borderRadius: 10,
            }}>
              {unreadCount}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="wv-live-dot" style={{ background: connected ? 'var(--wv-green)' : 'var(--text-muted)' }} />
          <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
            {connected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {loadingHistory && merged.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.72rem' }}>
          Loading...
        </div>
      ) : merged.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.72rem' }}>
          No alerts yet. The system is monitoring all active cameras.
        </div>
      ) : (
        <div style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
          {merged.map(a => (
            <AlertRow
              key={a.alert_uuid}
              alert={a}
              onAck={() => acknowledge(a.alert_uuid)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
