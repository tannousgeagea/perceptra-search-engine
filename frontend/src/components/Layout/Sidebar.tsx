import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Search, FolderOpen, Upload,
  BarChart3, Settings, LogOut, ChevronLeft, ChevronRight,
  Flame, Sun, Moon, Monitor, AlertTriangle, Bell, FileText, Columns2, ClipboardCheck,
  ScanLine,
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import { logoutUser } from '../../api/client'

const NAV_ITEMS = [
  { icon: LayoutDashboard, label: 'Dashboard',     path: '/dashboard' },
  { icon: Bell,            label: 'Alerts',         path: '/alerts' },
  { icon: Search,          label: 'Search',         path: '/search' },
  { icon: FolderOpen,      label: 'Media Library',  path: '/media' },
  { icon: Upload,          label: 'Upload',          path: '/upload' },
  { icon: BarChart3,       label: 'Analytics',       path: '/analytics' },
  { icon: FileText,        label: 'Reports',          path: '/reports' },
  { icon: Columns2,        label: 'Compare',          path: '/compare' },
  { icon: AlertTriangle,   label: 'Hazard Config',   path: '/hazard-config' },
  { icon: ClipboardCheck,  label: 'Checklists',      path: '/checklists' },
  { icon: ScanLine,        label: 'WasteVision',     path: '/wastevision' },
  { icon: Settings,        label: 'Settings',        path: '/settings' },
]

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const { auth, session, logout, displayName } = useAuth()
  const { theme, setTheme } = useTheme()
  const navigate = useNavigate()

  const handleLogout = async () => {
    if (auth?.mode === 'jwt' && auth.refreshToken) {
      logoutUser({ refresh: auth.refreshToken }).catch(() => {/* best-effort */})
    }
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <nav
      style={{
        width: collapsed ? 'var(--sidebar-collapsed)' : 'var(--sidebar-width)',
        transition: 'width var(--transition-slow)',
        flexShrink: 0,
        background: 'var(--bg-void)',
        borderRight: '1px solid var(--border-base)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        position: 'relative',
        zIndex: 100,
      }}
    >
      {/* Scan-line accent */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
        backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(245,166,35,0.012) 2px, rgba(245,166,35,0.012) 4px)',
        pointerEvents: 'none', zIndex: 0,
      }} />

      {/* Logo */}
      <div style={{
        padding: '20px 18px',
        borderBottom: '1px solid var(--border-dim)',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        position: 'relative', zIndex: 1,
        minHeight: 68,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'linear-gradient(135deg, var(--amber-600), var(--amber))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          boxShadow: '0 0 16px rgba(245,166,35,0.4)',
        }}>
          <Flame size={18} color="#000" strokeWidth={2.5} />
        </div>
        {!collapsed && (
          <div style={{ animation: 'fadeIn 0.2s ease-out' }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontWeight: 700,
              fontSize: 18, letterSpacing: '0.08em', color: 'var(--text-primary)',
              lineHeight: 1.1,
            }}>
              OPTI
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: 9,
              color: 'var(--amber)', letterSpacing: '0.2em',
            }}>
              VYN
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div style={{ flex: 1, padding: '12px 8px', position: 'relative', zIndex: 1, overflowY: 'auto' }}>
        {NAV_ITEMS.map(({ icon: Icon, label, path }) => (
          <NavLink
            key={path}
            to={path}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: collapsed ? '10px 18px' : '10px 14px',
              borderRadius: 'var(--radius-md)',
              marginBottom: 2,
              transition: 'all var(--transition-fast)',
              fontFamily: 'var(--font-display)',
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: '0.06em',
              textTransform: 'uppercase' as const,
              color: isActive ? 'var(--amber)' : 'var(--text-secondary)',
              background: isActive ? 'var(--amber-glow)' : 'transparent',
              borderLeft: `2px solid ${isActive ? 'var(--amber)' : 'transparent'}`,
              textDecoration: 'none',
              position: 'relative' as const,
              overflow: 'hidden',
              justifyContent: collapsed ? 'center' : 'flex-start',
            })}
          >
            {({ isActive }) => (
              <>
                <Icon size={17} strokeWidth={isActive ? 2.5 : 2} style={{ flexShrink: 0 }} />
                {!collapsed && (
                  <span style={{ animation: 'fadeIn 0.15s ease-out', whiteSpace: 'nowrap' }}>
                    {label}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </div>

      {/* System status */}
      {!collapsed && (
        <div style={{
          margin: '0 8px 8px',
          padding: '10px 12px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-dim)',
          borderRadius: 'var(--radius-md)',
          position: 'relative', zIndex: 1,
        }}>
          <div className="flex items-center gap-2">
            <span className="status-dot" />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--success)', letterSpacing: '0.1em' }}>
              SYSTEM ONLINE
            </span>
          </div>
        </div>
      )}

      {/* Theme toggle */}
      <div style={{
        padding: collapsed ? '8px' : '8px 12px',
        margin: '0 8px 4px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-dim)',
        borderRadius: 'var(--radius-md)',
        position: 'relative', zIndex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'space-between',
        gap: 4,
      }}>
        {collapsed ? (
          /* Collapsed: single button that cycles light → dark → system */
          <button
            onClick={() => {
              const next = theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light'
              setTheme(next)
            }}
            className="theme-btn active"
            title={`Theme: ${theme}`}
          >
            {theme === 'light' ? <Sun size={13} /> : theme === 'dark' ? <Moon size={13} /> : <Monitor size={13} />}
          </button>
        ) : (
          <>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 10,
              color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase',
            }}>
              Theme
            </span>
            <div style={{ display: 'flex', gap: 2 }}>
              {([
                { mode: 'light' as const, Icon: Sun,     title: 'Light' },
                { mode: 'dark' as const,  Icon: Moon,    title: 'Dark' },
                { mode: 'system' as const,Icon: Monitor, title: 'System' },
              ]).map(({ mode, Icon, title }) => (
                <button
                  key={mode}
                  onClick={() => setTheme(mode)}
                  className={`theme-btn${theme === mode ? ' active' : ''}`}
                  title={title}
                >
                  <Icon size={13} />
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* User + Logout */}
      <div style={{
        padding: '12px 8px',
        borderTop: '1px solid var(--border-dim)',
        position: 'relative', zIndex: 1,
      }}>
        {!collapsed && (
          <div style={{
            padding: '8px 14px',
            marginBottom: 6,
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{
              width: 30, height: 30, borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--amber-700), var(--amber-500))',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
              fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13, color: '#000',
            }}>
              {displayName[0]?.toUpperCase() ?? 'I'}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {displayName}
              </div>
              <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', letterSpacing: '0.06em' }}>
                {session?.role?.toUpperCase() ?? 'INSPECTOR'}
              </div>
            </div>
          </div>
        )}

        <button
          onClick={handleLogout}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            gap: 8,
            width: '100%',
            padding: collapsed ? '10px 18px' : '9px 14px',
            borderRadius: 'var(--radius-md)',
            fontFamily: 'var(--font-display)',
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            transition: 'all var(--transition-fast)',
            cursor: 'pointer',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--danger)'
            e.currentTarget.style.background = 'var(--danger-dim)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.background = 'transparent'
          }}
        >
          <LogOut size={15} />
          {!collapsed && <span>Sign Out</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        style={{
          position: 'absolute',
          top: 20,
          right: -12,
          width: 24,
          height: 24,
          borderRadius: '50%',
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-bright)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          zIndex: 200,
          color: 'var(--text-secondary)',
          transition: 'all var(--transition-fast)',
          boxShadow: 'var(--shadow-sm)',
        }}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed
          ? <ChevronRight size={13} />
          : <ChevronLeft size={13} />
        }
      </button>
    </nav>
  )
}
