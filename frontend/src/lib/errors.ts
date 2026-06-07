import { ApiError } from "../api/client"

export function getErrorMessage(error: unknown, fallback = "Request failed") {
  if (error instanceof ApiError) {
    const detail = error.detail ?? error.message

    if (error.status === 404) return detail || "Resource not found"
    if (error.status === 409) return detail || "Action conflict"
    if (error.status === 502) return detail || "Upstream service failure"

    return `${detail || fallback} (HTTP ${error.status})`
  }

  if (error instanceof Error) return error.message
  return fallback
}
