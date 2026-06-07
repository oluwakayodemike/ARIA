export type Phase =
  | "idle"
  | "auditing"
  | "profiling"
  | "generating"
  | "awaiting_approval"
  | "done"
  | "error"

export type LogLevel = "info" | "warning" | "error"

export interface ReasoningLogEntry {
  timestamp: string
  agent: string
  level: LogLevel
  message: string
}

export interface StateSummary {
  run_id: string
  phase: Phase
  coverage_score: number
  total_techniques: number
  covered_count: number
  partial_count: number
  gap_count: number
  pending_approvals: number
  error_count: number
  reasoning_log: ReasoningLogEntry[]

  coverage_before: number
  coverage_after: number
  gaps_identified: number
  rules_generated: number
  rules_approved: number
  rules_deployed: number
  avg_generation_time: number
  analyst_minutes_saved_estimate: number
}

export interface HealthResponse {
  status: "ok"
  is_running: boolean
  phase: Phase
}

export interface Technique {
  technique_id: string
  technique_name: string
  verdict: "COVERED" | "PARTIAL" | "GAP" | string
  tactics: string[]
  total_rules: number
  enabled_rules: number
  enabled_percentage: number
  description: string
  detection: string
  attack_profile: Record<string, unknown> | null
  generated_rule: string | null
  rule_explanation: string | null
  rule_confidence: number | null
  rule_provider: string | null
  rule_provider_trace: string[]
  pending_approval: boolean
  approved: boolean
  rejected: boolean
  deployed: boolean
}

export interface TechniquesResponse {
  techniques: Technique[]
  total: number
}

export interface PendingResponse {
  pending: Technique[]
  count: number
}

export interface RunResponse {
  status: "started"
  gap_limit: number
}

export interface ApproveResponse {
  status: "approved"
  technique_id: string
}

export interface RejectResponse {
  status: "rejected"
  technique_id: string
}

export interface ApiErrorPayload {
  detail?: string
}
