import { createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api/client"
import { queryKeys } from "../lib/queryKeys"

export const Route = createFileRoute("/approvals")({
  component: ApprovalsPage,
})

function ApprovalsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.pending,
    queryFn: api.getPending,
  })

  if (isLoading) {
    return <p className="text-ink-secondary">Loading pending approvals…</p>
  }

  if (isError) {
    const message =
      error instanceof Error
        ? error.message
        : "Failed to load pending approvals."
    return <p className="text-verdict-gap">{message}</p>
  }

  const pending = data?.pending ?? []

  return (
    <section className="space-y-4">
      <header className="glass-card p-4">
        <p className="muted-label">Human Review</p>
        <h1 className="mt-1 text-2xl font-semibold text-accent-glow">
          Approvals Queue
        </h1>
        <p className="mt-1 text-sm text-ink-secondary">
          Rules staged by Gap Agent awaiting analyst action.
        </p>
      </header>

      {!pending.length ? (
        <div className="glass-card p-4">
          <p className="text-ink-secondary">No pending approvals right now.</p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {pending.map((technique) => (
            <article
              key={technique.technique_id}
              className="glass-card border-l-2 border-l-accent-primary/70 p-4"
            >
              <p className="font-mono text-sm text-accent-glow">
                {technique.technique_id}
              </p>
              <p className="mt-1 text-ink-primary">
                {technique.technique_name}
              </p>
              <p className="mt-2 text-xs text-ink-secondary">
                Confidence: {technique.rule_confidence ?? "N/A"}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
