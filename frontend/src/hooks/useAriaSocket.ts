import { useEffect, useRef, useState } from "react"
import type { StateSummary } from "../types/api"

type SocketStatus = "connecting" | "connected" | "reconnecting" | "disconnected"

interface UseAriaSocketOptions {
  onState: (state: StateSummary) => void
}

function getSocketUrl() {
  const configuredBase = import.meta.env.VITE_API_BASE_URL as string | undefined

  if (configuredBase) {
    if (configuredBase.startsWith("https://")) {
      return configuredBase.replace("https://", "wss://") + "/ws"
    }
    if (configuredBase.startsWith("http://")) {
      return configuredBase.replace("http://", "ws://") + "/ws"
    }
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws"
  return `${protocol}://localhost:8080/ws`
}

export function useAriaSocket({ onState }: UseAriaSocketOptions) {
  const [status, setStatus] = useState<SocketStatus>("connecting")
  const [lastError, setLastError] = useState<string | null>(null)

  const reconnectTimerRef = useRef<number | null>(null)
  const retryRef = useRef(0)

  useEffect(() => {
    let isMounted = true
    let socket: WebSocket | null = null

    const clearRetryTimer = () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }

    const scheduleReconnect = () => {
      clearRetryTimer()

      const attempt = retryRef.current + 1
      retryRef.current = attempt

      const backoffMs = Math.min(10_000, 1_000 * 2 ** (attempt - 1))
      if (isMounted) {
        setStatus("reconnecting")
      }

      reconnectTimerRef.current = window.setTimeout(() => {
        if (!isMounted) return
        connect()
      }, backoffMs)
    }

    const connect = () => {
      clearRetryTimer()

      if (isMounted && retryRef.current === 0) {
        setStatus("connecting")
      }

      try {
        socket = new WebSocket(getSocketUrl())
      } catch (error) {
        if (isMounted) {
          setLastError(error instanceof Error ? error.message : "WebSocket init failed")
          setStatus("disconnected")
        }
        scheduleReconnect()
        return
      }

      socket.onopen = () => {
        if (!isMounted) return
        retryRef.current = 0
        setLastError(null)
        setStatus("connected")
      }

      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as StateSummary
          onState(parsed)
        } catch {
          if (isMounted) {
            setLastError("Received invalid state payload from WebSocket")
          }
        }
      }

      socket.onerror = () => {
        if (!isMounted) return
        setLastError("WebSocket connection error")
      }

      socket.onclose = () => {
        if (!isMounted) return
        setStatus("disconnected")
        scheduleReconnect()
      }
    }

    connect()

    return () => {
      isMounted = false
      clearRetryTimer()
      if (socket) {
        socket.onclose = null
        socket.close()
      }
    }
  }, [onState])

  return {
    status,
    isConnected: status === "connected",
    lastError,
  }
}
