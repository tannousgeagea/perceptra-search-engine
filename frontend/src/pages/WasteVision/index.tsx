import { useEffect, useState } from 'react'
import { ScanLine, Activity, AlertTriangle, FileText, Settings2 } from 'lucide-react'
import type { WasteCamera, WasteStats } from '../../types/api'
import { listWasteCameras, getWasteStats } from '../../api/client'
import './wastevision.css'
import CameraGrid from './CameraGrid'
import CompositionPanel from './CompositionPanel'
import AlertFeed from './AlertFeed'
import InspectorLog from './InspectorLog'
import CameraManager from './CameraManager'
import EmbedWidget from './EmbedWidget'

type Tab = 'cameras' | 'composition' | 'alerts' | 'log' | 'manage'

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: 'cameras',     label: 'Cameras',     icon: ScanLine },
  { id: 'composition', label: 'Composition', icon: Activity },
  { id: 'alerts',      label: 'Alerts',      icon: AlertTriangle },
  { id: 'log',         label: 'Inspector Log', icon: FileText },
  { id: 'manage',      label: 'Manage',      icon: Settings2 },
]

function StatCard({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="wv-panel" style={{ padding: '12px 18px', minWidth: 120 }}>
      <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: '1.4rem', fontWeight: 700, letterSpacing: '-0.02em', color: accent ?? 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  )
}

export default function WasteVisionPage() {
  // Check embed mode
  const isEmbed = new URLSearchParams(window.location.search).get('embed') === '1'
  if (isEmbed) return <EmbedWidget />

  const [activeTab, setActiveTab] = useState<Tab>('cameras')
  const [cameras, setCameras] = useState<WasteCamera[]>([])
  const [stats, setStats] = useState<WasteStats | null>(null)
  const [loadingCameras, setLoadingCameras] = useState(true)

  const loadCameras = () => {
    setLoadingCameras(true)
    listWasteCameras({ page_size: 100 })
      .then(r => setCameras(r.data.items))
      .catch(() => {})
      .finally(() => setLoadingCameras(false))
  }

  const loadStats = () => {
    getWasteStats()
      .then(r => setStats(r.data))
      .catch(() => {})
  }

  useEffect(() => {
    loadCameras()
    loadStats()
    const interval = setInterval(loadStats, 30_000)
    return () => clearInterval(interval)
  }, [])

  const criticalAlerts = stats?.risk_breakdown?.critical ?? 0

  return (
    <div className="wv-root" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="wv-scanlines" />

      {/* Header */}
      <div className="wv-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ScanLine size={18} color="var(--wv-green)" />
          <span className="wv-header-title">WasteVision</span>
          <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
            AUTOMATED WASTE INSPECTION SYSTEM
          </span>
        </div>
        <div className="wv-header-meta">
          {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          &nbsp;·&nbsp;
          {cameras.filter(c => c.status === 'streaming').length} active streams
        </div>
      </div>

      {/* Stats strip */}
      {stats && (
        <div style={{
          display: 'flex', gap: 10, padding: '10px 16px',
          borderBottom: '1px solid var(--wv-border)',
          overflowX: 'auto',
        }}>
          <StatCard label="Total Inspections" value={stats.total_inspections.toLocaleString()} />
          <StatCard label="Active Cameras" value={stats.active_cameras} accent="var(--wv-green)" />
          <StatCard label="Alerts / 24h" value={stats.alerts_last_24h} accent={stats.alerts_last_24h > 0 ? 'var(--wv-amber)' : undefined} />
          <StatCard label="Critical" value={criticalAlerts} accent={criticalAlerts > 0 ? 'var(--wv-red)' : undefined} />
          <StatCard label="High Risk" value={stats.risk_breakdown?.high ?? 0} accent="var(--wv-amber)" />
        </div>
      )}

      {/* Tab bar */}
      <div className="wv-tabs">
        {TABS.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              className={`wv-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <Icon size={13} />
              {tab.label}
              {tab.id === 'alerts' && criticalAlerts > 0 && (
                <span style={{
                  background: 'var(--wv-red)', color: '#fff',
                  fontSize: '0.55rem', padding: '1px 5px', borderRadius: 8, marginLeft: 2,
                }}>
                  {criticalAlerts}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflowY: 'auto', position: 'relative', zIndex: 1 }}>
        {loadingCameras && activeTab !== 'manage' ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.72rem' }}>
            Loading cameras...
          </div>
        ) : (
          <>
            {activeTab === 'cameras'     && <CameraGrid cameras={cameras} />}
            {activeTab === 'composition' && <CompositionPanel cameras={cameras} />}
            {activeTab === 'alerts'      && <AlertFeed />}
            {activeTab === 'log'         && <InspectorLog cameras={cameras} />}
            {activeTab === 'manage'      && <CameraManager cameras={cameras} onRefresh={loadCameras} />}
          </>
        )}
      </div>
    </div>
  )
}
