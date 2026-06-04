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
  const socketRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(0)

  useEffect(() => {
    let isMounted = true

    const clearRetryTimer = () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }

    const closeActiveSocket = () => {
      const active = socketRef.current
      if (!active) return
      active.onclose = null
      active.close()
      socketRef.current = null
    }

    const scheduleReconnect = () => {
      if (!isMounted) return
      if (!window.navigator.onLine) {
        setStatus("disconnected")
        setLastError("Network offline. Waiting to reconnect...")
        return
      }

      clearRetryTimer()

      const attempt = retryRef.current + 1
      retryRef.current = attempt

      const backoffMs = Math.min(10_000, 1_000 * 2 ** (attempt - 1))
      const jitterMs = Math.floor(Math.random() * 250)
      setStatus("reconnecting")

      reconnectTimerRef.current = window.setTimeout(() => {
        if (!isMounted) return
        connect()
      }, backoffMs + jitterMs)
    }

    const connect = () => {
      if (!isMounted) return
      if (!window.navigator.onLine) {
        setStatus("disconnected")
        setLastError("Network offline. Waiting to reconnect...")
        return
      }

      clearRetryTimer()
      closeActiveSocket()

      if (retryRef.current === 0) {
        setStatus("connecting")
      }

      let socket: WebSocket
      try {
        socket = new WebSocket(getSocketUrl())
      } catch (error) {
        setLastError(
          error instanceof Error ? error.message : "WebSocket init failed",
        )
        setStatus("disconnected")
        scheduleReconnect()
        return
      }

      socketRef.current = socket

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
        socketRef.current = null
        setStatus("disconnected")
        scheduleReconnect()
      }
    }

    const handleOnline = () => {
      if (!isMounted) return
      setLastError(null)
      retryRef.current = 0
      connect()
    }

    const handleOffline = () => {
      if (!isMounted) return
      clearRetryTimer()
      closeActiveSocket()
      setStatus("disconnected")
      setLastError("Network offline. Waiting to reconnect...")
    }

    window.addEventListener("online", handleOnline)
    window.addEventListener("offline", handleOffline)

    connect()

    return () => {
      isMounted = false
      clearRetryTimer()
      window.removeEventListener("online", handleOnline)
      window.removeEventListener("offline", handleOffline)
      closeActiveSocket()
    }
  }, [onState])

  return {
    status,
    isConnected: status === "connected",
    lastError,
  }
}
