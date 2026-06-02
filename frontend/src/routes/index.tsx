import { createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api/client"
import { queryKeys } from "../lib/queryKeys"

export const Route = createFileRoute("/")({
  component: OverviewPage,
})

function OverviewPage() {
  const {
    data: state,
    isLoading: isStateLoading,
    isError: isStateError,
    error: stateError,
  } = useQuery({
    queryKey: queryKeys.state,
    queryFn: api.getState,
    refetchInterval: 5000,
  })

  const {
    data: pending,
    isLoading: isPendingLoading,
    isError: isPendingError,
    error: pendingError,
  } = useQuery({
    queryKey: queryKeys.pending,
    queryFn: api.getPending,
    refetchInterval: 5000,
  })

  return (
    <section className="space-y-5">
      <header>
        <p className="muted-label">Overview</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-accent-glow">
          War Room Status
        </h1>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          title="Total Techniques"
          value={state?.total_techniques ?? "—"}
          loading={isStateLoading}
          error={isStateError ? getErrorText(stateError) : null}
        />
        <MetricCard
          title="Pending Approvals"
          value={pending?.count ?? state?.pending_approvals ?? "—"}
          loading={isPendingLoading}
          error={isPendingError ? getErrorText(pendingError) : null}
        />
      </div>

      <div className="glass-card p-4 md:p-5">
        <h2 className="panel-heading">Recent Reasoning Log</h2>
        <p className="panel-subtext mt-1">
          Latest decisions and processing messages from the pipeline.
        </p>

        <div className="mt-4">
          {isStateLoading ? (
            <p className="text-ink-secondary">Loading state…</p>
          ) : isStateError ? (
            <p className="text-verdict-gap">{getErrorText(stateError)}</p>
          ) : !state?.reasoning_log?.length ? (
            <p className="text-ink-secondary">No log entries yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {state.reasoning_log.map((entry) => (
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
