import { createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api/client"
import { queryKeys } from "../lib/queryKeys"

export const Route = createFileRoute("/techniques/$techniqueId")({
  component: TechniqueDetailPage,
})

function TechniqueDetailPage() {
  const { techniqueId } = Route.useParams()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.technique(techniqueId),
    queryFn: () => api.getTechnique(techniqueId),
  })

  if (isLoading) {
    return <p className="text-ink-secondary">Loading technique details…</p>
  }

  if (isError) {
    const message =
      error instanceof Error
        ? error.message
        : "Failed to load technique details."
    return <p className="text-verdict-gap">{message}</p>
  }

  if (!data) {
    return <p className="text-ink-secondary">Technique not found.</p>
  }

  return (
    <section className="space-y-4">
      <header className="glass-card p-4">
        <p className="muted-label">Technique Detail</p>
        <h1 className="mt-1 font-mono text-2xl text-accent-glow">
          {data.technique_id}
        </h1>
        <p className="mt-1 text-ink-secondary">{data.technique_name}</p>
      </header>

      <div className="glass-card p-4">
        <h2 className="panel-heading">Coverage Snapshot</h2>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-ink-muted">Verdict</dt>
            <dd className="mt-1">{data.verdict}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Tactics</dt>
            <dd className="mt-1">{data.tactics.join(", ") || "N/A"}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Coverage</dt>
            <dd className="mt-1">
              {data.enabled_rules}/{data.total_rules}
            </dd>
          </div>
          <div>
            <dt className="text-ink-muted">Pending approval</dt>
            <dd className="mt-1">{data.pending_approval ? "Yes" : "No"}</dd>
          </div>
        </dl>
      </div>

      <div className="glass-card p-4">
        <h2 className="panel-heading">Generated Rule</h2>
        {data.generated_rule ? (
          <pre className="mt-3 overflow-auto whitespace-pre-wrap rounded-lg border border-surface-600/70 bg-surface-800/85 p-3 text-xs text-ink-primary">
            {data.generated_rule}
          </pre>
        ) : (
          <p className="mt-2 text-ink-secondary">No rule generated yet.</p>
        )}
      </div>
    </section>
  )
}
