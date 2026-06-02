import { useState } from "react"
import { Link, Outlet, createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api/client"
import { queryKeys } from "../lib/queryKeys"

export const Route = createFileRoute("/techniques")({
  component: TechniquesPage,
})

function TechniquesPage() {
  const [verdictFilter, setVerdictFilter] = useState<
    "ALL" | "COVERED" | "PARTIAL" | "GAP"
  >("ALL")

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.techniques(
      verdictFilter === "ALL" ? undefined : verdictFilter,
    ),
    queryFn: () =>
      api.getTechniques(verdictFilter === "ALL" ? undefined : verdictFilter),
  })

  const techniques = data?.techniques ?? []

  return (
    <section className="space-y-4">
      <header className="glass-card flex flex-wrap items-center justify-between gap-4 p-4">
        <div>
          <p className="muted-label">Coverage Catalog</p>
          <h1 className="mt-1 text-2xl font-semibold text-accent-glow">
            Techniques
          </h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Browse ARIA technique coverage and detection status.
          </p>
        </div>

        <label className="text-sm text-ink-secondary">
          Verdict
          <select
            value={verdictFilter}
            onChange={(event) =>
              setVerdictFilter(
                event.target.value as "ALL" | "COVERED" | "PARTIAL" | "GAP",
              )
            }
            className="ml-2 rounded-md border border-surface-600 bg-surface-800 px-2.5 py-1.5 text-ink-primary outline-none ring-accent-primary/40 focus:ring"
          >
            <option value="ALL">ALL</option>
            <option value="COVERED">COVERED</option>
            <option value="PARTIAL">PARTIAL</option>
            <option value="GAP">GAP</option>
          </select>
        </label>
      </header>

      {isLoading ? (
        <p className="text-ink-secondary">Loading techniques…</p>
      ) : isError ? (
        <p className="text-verdict-gap">
          {error instanceof Error
            ? error.message
            : "Failed to load techniques."}
        </p>
      ) : !techniques.length ? (
        <div className="glass-card p-4">
          <p className="text-ink-secondary">
            No techniques found for this filter.
          </p>
        </div>
      ) : (
        <div className="glass-card overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-surface-800/80 text-ink-secondary">
              <tr>
                <th className="px-4 py-3">Technique</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Verdict</th>
                <th className="px-4 py-3">Rules</th>
                <th className="px-4 py-3">Pending</th>
              </tr>
            </thead>
            <tbody>
              {techniques.map((technique) => (
                <tr
                  key={technique.technique_id}
                  className="border-t border-surface-600/70 transition-colors hover:bg-surface-800/45"
                >
                  <td className="px-4 py-3 font-mono">
                    <Link
                      to="/techniques/$techniqueId"
                      params={{ techniqueId: technique.technique_id }}
                      className="text-accent-glow hover:underline"
                    >
                      {technique.technique_id}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{technique.technique_name}</td>
                  <td className="px-4 py-3">
                    <span className={badgeClass(technique.verdict)}>
                      {technique.verdict}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-ink-secondary">
                    {technique.enabled_rules}/{technique.total_rules}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        technique.pending_approval
                          ? "text-accent-glow"
                          : "text-ink-muted"
                      }
                    >
                      {technique.pending_approval ? "Queued" : "No"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section className="space-y-2">
        <p className="muted-label">Technique Inspector</p>
        <div className="glass-card p-4">
          <Outlet />
        </div>
      </section>
    </section>
  )
}

function badgeClass(verdict: string) {
  if (verdict === "COVERED") {
    return "verdict-covered inline-flex rounded-md px-2 py-1 text-xs font-semibold"
  }

  if (verdict === "PARTIAL") {
    return "verdict-partial inline-flex rounded-md px-2 py-1 text-xs font-semibold"
  }

  return "verdict-gap inline-flex rounded-md px-2 py-1 text-xs font-semibold"
}
