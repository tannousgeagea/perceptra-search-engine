import {
  createContext, useContext, useState, useCallback, useEffect, useRef,
  type ReactNode,
} from 'react'
import type { AlertResponse } from '../types/api'
import { getAlertUnreadCount } from '../api/client'
import { useAuth } from './AuthContext'

interface AlertContextValue {
  unreadCount: number
  recentAlerts: AlertResponse[]
  refreshUnreadCount: () => void
  addRealtimeAlert: (alert: AlertResponse) => void
  clearRecent: () => void
}

const AlertContext = createContext<AlertContextValue | null>(null)

export function AlertProvider({ children }: { children: ReactNode }) {
  const { auth, isAuthenticated } = useAuth()
  const [unreadCount, setUnreadCount] = useState(0)
  const [recentAlerts, setRecentAlerts] = useState<AlertResponse[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const refreshUnreadCount = useCallback(() => {
    if (!isAuthenticated) return
    getAlertUnreadCount().then((r) => setUnreadCount(r.data.count)).catch(() => {})
  }, [isAuthenticated])

  const addRealtimeAlert = useCallback((alert: AlertResponse) => {
    setRecentAlerts((prev) => [alert, ...prev].slice(0, 20))
    setUnreadCount((c) => c + 1)
  }, [])

  const clearRecent = useCallback(() => {
    setRecentAlerts([])
  }, [])

  // Poll unread count periodically
  useEffect(() => {
    if (!isAuthenticated) return
    refreshUnreadCount()
    const interval = setInterval(refreshUnreadCount, 30000)
    return () => clearInterval(interval)
  }, [isAuthenticated, refreshUnreadCount])

  // WebSocket connection for real-time alerts
  useEffect(() => {
    if (!isAuthenticated || !auth) return

    const connect = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const host = window.location.host
        let wsUrl: string

        if (auth.mode === 'jwt' && auth.token) {
          wsUrl = `${protocol}//${host}/api/v1/alerts/ws?token=${auth.token}`
        } else if (auth.mode === 'apikey' && auth.apiKey) {
          wsUrl = `${protocol}//${host}/api/v1/alerts/ws?api_key=${auth.apiKey}`
        } else {
          return
        }

        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.type === 'new_alert' && data.alert) {
              addRealtimeAlert(data.alert as AlertResponse)
            }
          } catch { /* ignore parse errors */ }
        }

        ws.onclose = () => {
          wsRef.current = null
          // Auto-reconnect after 5 seconds
          reconnectTimer.current = setTimeout(connect, 5000)
        }

        ws.onerror = () => {
          ws.close()
        }
      } catch {
        // WebSocket not available, fall back to polling only
      }
    }

    connect()

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [isAuthenticated, auth, addRealtimeAlert])

  const value: AlertContextValue = {
    unreadCount,
    recentAlerts,
    refreshUnreadCount,
    addRealtimeAlert,
    clearRecent,
  }

  return <AlertContext.Provider value={value}>{children}</AlertContext.Provider>
}

export function useAlerts(): AlertContextValue {
  const ctx = useContext(AlertContext)
  if (!ctx) throw new Error('useAlerts must be used within AlertProvider')
  return ctx
}
