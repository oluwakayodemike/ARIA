import { useCallback, useEffect, useState } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "../api/client"
import { useAriaSocket } from "../hooks/useAriaSocket"
import { queryKeys } from "../lib/queryKeys"
import type { StateSummary } from "../types/api"

export const Route = createFileRoute("/")({
  component: OverviewPage,
})

function OverviewPage() {
  const queryClient = useQueryClient()
  const [gapLimit, setGapLimit] = useState(3)

  const handleSocketState = useCallback(
    (nextState: StateSummary) => {
      queryClient.setQueryData(queryKeys.state, nextState)
    },
    [queryClient],
  )

  const socket = useAriaSocket({ onState: handleSocketState })

  const {
    data: state,
    isLoading: isStateLoading,
    isError: isStateError,
    error: stateError,
  } = useQuery({
    queryKey: queryKeys.state,
    queryFn: api.getState,
    refetchInterval: socket.isConnected ? false : 5000,
  })

  const {
    data: health,
    isLoading: isHealthLoading,
    isError: isHealthError,
    error: healthError,
  } = useQuery({
    queryKey: queryKeys.health,
    queryFn: api.getHealth,
    refetchInterval: socket.isConnected ? false : 5000,
  })

  const startRunMutation = useMutation({
    mutationFn: (limit: number) => api.startRun(limit),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.health }),
        queryClient.invalidateQueries({ queryKey: queryKeys.state }),
      ])
    },
  })

  useEffect(() => {
    if (socket.isConnected) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.state })
      void queryClient.invalidateQueries({ queryKey: queryKeys.health })
    }
  }, [queryClient, socket.isConnected])

  const logEntries = state?.reasoning_log?.slice(-14).reverse() ?? []

  const canStartRun = !startRunMutation.isPending && !health?.is_running
  const hasStateData =
    !!state &&
    (state.total_techniques > 0 ||
      state.reasoning_log.length > 0 ||
      state.phase !== "idle")

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="muted-label">Overview</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-accent-glow">
            War Room Status
          </h1>
        </div>

        <div className="flex items-center gap-2 rounded-full border border-surface-600/70 bg-surface-800/70 px-3 py-1.5 text-xs text-ink-secondary">
          <span
            className={[
              "h-2 w-2 rounded-full",
              socket.status === "connected"
                ? "bg-verdict-covered"
                : socket.status === "reconnecting"
                  ? "bg-verdict-partial"
                  : "bg-verdict-gap",
            ].join(" ")}
          />
          <span>Socket {socket.status}</span>
        </div>
      </header>

      <div className="glass-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="muted-label">Pipeline Control</p>
            <p className="mt-1 text-sm text-ink-secondary">
              Start an ARIA run to refresh coverage and generate staged
              detections.
            </p>
            <label className="mt-2 inline-flex items-center gap-2 text-xs text-ink-secondary">
              Gap limit
              <input
                type="number"
                min={1}
                max={20}
                value={gapLimit}
                onChange={(event) => {
                  const parsed = Number.parseInt(event.target.value, 10)
                  if (Number.isNaN(parsed)) return
                  setGapLimit(Math.min(20, Math.max(1, parsed)))
                }}
                className="w-16 rounded-md border border-surface-600 bg-surface-800 px-2 py-1 text-ink-primary outline-none ring-accent-primary/40 focus:ring"
              />
            </label>
            {startRunMutation.isError ? (
              <p className="mt-2 text-sm text-verdict-gap">
                {getErrorText(startRunMutation.error)}
              </p>
            ) : null}
            {socket.lastError ? (
              <p className="mt-2 text-xs text-verdict-partial">
                Live stream issue: {socket.lastError} (fallback polling active)
              </p>
            ) : null}
          </div>

          <button
            type="button"
            onClick={() => startRunMutation.mutate(gapLimit)}
            disabled={!canStartRun}
            className="rounded-lg border border-accent-primary/45 bg-accent-primary/18 px-4 py-2 text-sm font-medium text-accent-glow transition hover:bg-accent-primary/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {startRunMutation.isPending
              ? "Starting..."
              : health?.is_running
                ? "Run in Progress"
                : "Start Run"}
          </button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <MetricCard
          title="Phase"
          value={state?.phase ?? "—"}
          loading={isStateLoading}
          error={isStateError ? getErrorText(stateError) : null}
        />
        <MetricCard
          title="Coverage Score"
          value={state ? `${state.coverage_score}%` : "—"}
          loading={isStateLoading}
          error={isStateError ? getErrorText(stateError) : null}
        />
        <MetricCard
          title="Covered"
          value={state?.covered_count ?? "—"}
          loading={isStateLoading}
          error={isStateError ? getErrorText(stateError) : null}
        />
        <MetricCard
          title="Partial"
          value={state?.partial_count ?? "—"}
          loading={isStateLoading}
          error={isStateError ? getErrorText(stateError) : null}
        />
        <MetricCard
          title="Gaps"
          value={state?.gap_count ?? "—"}
          loading={isStateLoading}
          error={isStateError ? getErrorText(stateError) : null}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="glass-card p-4 md:p-5">
          <h2 className="panel-heading">Live Reasoning Log</h2>
          <p className="panel-subtext mt-1">
            Latest decisions and processing messages from the pipeline.
          </p>

          <div className="mt-4">
            {isStateLoading ? (
              <p className="text-ink-secondary">Loading state…</p>
            ) : isStateError ? (
              <p className="text-verdict-gap">{getErrorText(stateError)}</p>
            ) : !logEntries.length ? (
              <p className="text-ink-secondary">No log entries yet.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {logEntries.map((entry) => (
                  <li
                    key={`${entry.timestamp}-${entry.agent}-${entry.message}`}
                    className="rounded-lg border border-surface-600/70 bg-surface-800/80 px-3 py-2"
                  >
                    <span className="mr-2 font-mono text-xs text-ink-muted">
                      [{entry.agent}]
                    </span>
                    <span className="text-ink-primary">{entry.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <aside className="glass-card p-4">
          <p className="muted-label">Run Status</p>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex items-center justify-between gap-2">
              <dt className="text-ink-muted">Pending approvals</dt>
              <dd className="text-accent-glow">
                {state?.pending_approvals ?? "—"}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-ink-muted">Total techniques</dt>
              <dd>{state?.total_techniques ?? "—"}</dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-ink-muted">Runner</dt>
              <dd>
                {isHealthLoading
                  ? "Checking…"
                  : health?.is_running
                    ? "Active"
                    : "Idle"}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-ink-muted">Health</dt>
              <dd>
                {isHealthError
                  ? getErrorText(healthError)
                  : health?.status === "ok"
                    ? "OK"
                    : "—"}
              </dd>
            </div>
          </dl>

          {!hasStateData ? (
            <div className="mt-4 rounded-lg border border-surface-600/70 bg-surface-800/75 p-3">
              <p className="text-xs text-ink-secondary">
                No run has been executed yet. Start a run to populate coverage,
                gaps, and live agent reasoning.
              </p>
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  )
}

function MetricCard({
  title,
  value,
  loading,
  error,
}: {
  title: string
  value: string | number
  loading: boolean
  error: string | null
}) {
  return (
    <article className="glass-card p-4">
      <p className="muted-label">{title}</p>
      {loading ? (
        <p className="mt-2 text-sm text-ink-secondary">Loading…</p>
      ) : error ? (
        <p className="mt-2 text-sm text-verdict-gap">{error}</p>
      ) : (
        <p className="mt-2 text-2xl font-semibold text-accent-glow">{value}</p>
      )}
    </article>
  )
}

function getErrorText(error: unknown): string {
  if (error instanceof Error) return error.message
  return "Request failed."
}
