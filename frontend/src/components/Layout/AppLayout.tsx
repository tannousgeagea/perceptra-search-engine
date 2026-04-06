import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Bell } from 'lucide-react'
import Sidebar from './Sidebar'
import AlertPanel from '../AlertPanel'
import { useAlerts } from '../../context/AlertContext'

const PAGE_NAMES: Record<string, string> = {
  '/dashboard':  'Dashboard',
  '/search':     'Visual Search',
  '/media':      'Media Vault',
  '/upload':     'Data Upload',
  '/analytics':  'System Analytics',
  '/settings':   'Configuration',
  '/alerts':     'Alerts',
  '/reports':    'Shift Reports',
  '/checklists': 'Checklists',
  '/compare':    'Compare',
}

export default function AppLayout() {
  const { pathname } = useLocation()
  const pageName = PAGE_NAMES[pathname] ?? ''
  const { unreadCount } = useAlerts()
  const [alertPanelOpen, setAlertPanelOpen] = useState(false)

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        {/* Top bar */}
        <div className="top-bar">
          <div className="flex items-center gap-3">
            <span style={{
              fontFamily: 'var(--font-display)',
              fontSize: 14,
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--text-secondary)',
            }}>
              {pageName}
            </span>
          </div>
          <div className="flex items-center gap-3">
            {/* Alert bell */}
            <button
              onClick={() => setAlertPanelOpen(true)}
              style={{
                position: 'relative',
                background: 'transparent',
                cursor: 'pointer',
                padding: 6,
                borderRadius: 'var(--radius-md)',
                color: unreadCount > 0 ? 'var(--amber)' : 'var(--text-muted)',
                transition: 'all var(--transition-fast)',
              }}
              title={`${unreadCount} unread alerts`}
            >
              <Bell size={16} />
              {unreadCount > 0 && (
                <span style={{
                  position: 'absolute', top: 2, right: 2,
                  minWidth: 16, height: 16, borderRadius: 8,
                  background: 'var(--danger)', color: '#fff',
                  fontSize: 9, fontWeight: 700, fontFamily: 'var(--font-mono)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: '0 4px',
                  boxShadow: '0 0 8px rgba(239,68,68,0.5)',
                }}>
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              )}
            </button>

            <div style={{ width: 1, height: 16, background: 'var(--border-base)' }} />

            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--text-muted)',
              letterSpacing: '0.06em',
            }}>
              API: <span style={{ color: 'var(--success)' }}>CONNECTED</span>
            </div>
            <div style={{
              width: 1, height: 16,
              background: 'var(--border-base)',
            }} />
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
              v1.0.0
            </div>
          </div>
        </div>

        {/* Page content */}
        <Outlet />
      </div>

      {/* Alert sliding panel */}
      <AlertPanel open={alertPanelOpen} onClose={() => setAlertPanelOpen(false)} />
    </div>
  )
}
