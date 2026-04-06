import { useEffect, useRef, useState } from 'react'
import type { WasteInspection } from '../../../types/api'

interface UseCameraStreamResult {
  latestInspection: WasteInspection | null
  connected: boolean
}

export function useCameraStream(cameraUuid: string | null): UseCameraStreamResult {
  const [latestInspection, setLatestInspection] = useState<WasteInspection | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!cameraUuid) return

    let cancelled = false

    const connect = () => {
      if (cancelled) return

      const raw = localStorage.getItem('auth')
      if (!raw) return
      const auth = JSON.parse(raw)
      const param = auth.mode === 'jwt' ? `token=${auth.token}` : `api_key=${auth.apiKey}`
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${proto}//${window.location.host}/api/v1/wastevision/cameras/${cameraUuid}/stream?${param}`

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          if (msg.type === 'frame_result' && msg.inspection) {
            setLatestInspection(msg.inspection as WasteInspection)
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
  }, [cameraUuid])

  return { latestInspection, connected }
}
