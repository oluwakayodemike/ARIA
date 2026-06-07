import type {
  ApiErrorPayload,
  ApproveResponse,
  PendingResponse,
  RejectResponse,
  RunResponse,
  StateSummary,
  Technique,
  TechniquesResponse,
  HealthResponse,
} from "../types/api"

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080"

export class ApiError extends Error {
  status: number
  detail?: string

  constructor(status: number, message: string, detail?: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    let detail: string | undefined

    try {
      const payload = (await response.json()) as ApiErrorPayload
      detail = payload?.detail
    } catch {
      detail = undefined
    }

    throw new ApiError(
      response.status,
      detail ?? `Request failed with ${response.status}`,
      detail,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export const api = {
  getHealth: () => request<HealthResponse>("/api/health"),

  getState: () => request<StateSummary>("/api/state"),

  startRun: (gapLimit = 10) =>
    request<RunResponse>("/api/run", {
      method: "POST",
      body: JSON.stringify({ gap_limit: gapLimit }),
    }),

  getTechniques: (verdict?: string) => {
    const params = new URLSearchParams()
    if (verdict) params.set("verdict", verdict)
    const query = params.toString()
    return request<TechniquesResponse>(
      `/api/techniques${query ? `?${query}` : ""}`,
    )
  },

  getTechnique: (techniqueId: string) =>
    request<Technique>(`/api/techniques/${encodeURIComponent(techniqueId)}`),

  getPending: () => request<PendingResponse>("/api/pending"),

  approve: (techniqueId: string) =>
    request<ApproveResponse>(
      `/api/approve/${encodeURIComponent(techniqueId)}`,
      {
        method: "POST",
      },
    ),

  reject: (techniqueId: string, reason = "") =>
    request<RejectResponse>(`/api/reject/${encodeURIComponent(techniqueId)}`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
}
