import { useCallback, useEffect, useRef, useState } from 'react'
import type { WasteAlert } from '../../../types/api'
import { acknowledgeWasteAlert } from '../../../api/client'

interface UseWasteAlertsResult {
  alerts: WasteAlert[]
  unreadCount: number
  connected: boolean
  acknowledge: (alertUuid: string) => Promise<void>
}

export function useWasteAlerts(): UseWasteAlertsResult {
  const [alerts, setAlerts] = useState<WasteAlert[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false

    const connect = () => {
      if (cancelled) return

      const raw = localStorage.getItem('auth')
      if (!raw) return
      const auth = JSON.parse(raw)
      const param = auth.mode === 'jwt' ? `token=${auth.token}` : `api_key=${auth.apiKey}`
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${proto}//${window.location.host}/api/v1/wastevision/alerts/stream?${param}`

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          if (msg.type === 'new_alert' && msg.alert?.source === 'wastevision') {
            const incoming = msg.alert as WasteAlert
            setAlerts((prev) => {
              const updated = [incoming, ...prev]
              return updated.slice(0, 200)
            })
          }
        } catch { /* ignore */ }
      }

      ws.onclose = () => {
        setConnected(false)
        if (!cancelled) {
          retryTimer.current = setTimeout(connect, 5000)
        }
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      cancelled = true
      if (retryTimer.current) clearTimeout(retryTimer.current)
      wsRef.current?.close()
    }
  }, [])

  const acknowledge = useCallback(async (alertUuid: string) => {
    await acknowledgeWasteAlert(alertUuid)
    setAlerts((prev) =>
      prev.map((a) =>
        a.alert_uuid === alertUuid
          ? { ...a, is_acknowledged: true, acknowledged_at: new Date().toISOString() }
          : a
      )
    )
  }, [])

  const unreadCount = alerts.filter((a) => !a.is_acknowledged).length

  return { alerts, unreadCount, connected, acknowledge }
}
