import { useMemo, useState } from "react"
import {
  Outlet,
  createFileRoute,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { api } from "../api/client"
import { queryKeys } from "../lib/queryKeys"

export const Route = createFileRoute("/techniques")({
  component: TechniquesPage,
})

function TechniquesPage() {
  const navigate = useNavigate()
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })

  const [verdictFilter, setVerdictFilter] = useState<
    "ALL" | "COVERED" | "PARTIAL" | "GAP"
  >("ALL")
  const [searchText, setSearchText] = useState("")

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.techniques(
      verdictFilter === "ALL" ? undefined : verdictFilter,
    ),
    queryFn: () =>
      api.getTechniques(verdictFilter === "ALL" ? undefined : verdictFilter),
  })

  const filteredTechniques = useMemo(() => {
    const techniques = data?.techniques ?? []
    const normalized = searchText.trim().toLowerCase()

    if (!normalized) return techniques

    return techniques.filter(
      (technique) =>
        technique.technique_id.toLowerCase().includes(normalized) ||
        technique.technique_name.toLowerCase().includes(normalized),
    )
  }, [data?.techniques, searchText])

  const isDetailOpen = pathname.startsWith("/techniques/")

  return (
    <section className="space-y-4">
      <header className="glass-card flex flex-wrap items-center justify-between gap-4 p-4">
        <div>
          <p className="muted-label">Coverage Catalog</p>
          <h1 className="mt-1 text-2xl font-semibold text-accent-glow">
            Techniques
          </h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Discover coverage posture and inspect generated detections.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-ink-secondary">
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

          <input
            type="search"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Search ID or name"
            className="rounded-md border border-surface-600 bg-surface-800 px-3 py-1.5 text-sm text-ink-primary outline-none ring-accent-primary/40 focus:ring"
          />
        </div>
      </header>

      {isLoading ? (
        <p className="text-ink-secondary">Loading techniques…</p>
      ) : isError ? (
        <p className="text-verdict-gap">
          {error instanceof Error
            ? error.message
            : "Failed to load techniques."}
        </p>
      ) : !(data?.techniques?.length ?? 0) ? (
        <div className="glass-card p-4">
          <p className="text-ink-secondary">
            No techniques found for this verdict filter.
          </p>
        </div>
      ) : !filteredTechniques.length ? (
        <div className="glass-card p-4">
          <p className="text-ink-secondary">
            No techniques matched your search query.
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
                <th className="px-4 py-3">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {filteredTechniques.map((technique) => (
                <tr
                  key={technique.technique_id}
                  className="cursor-pointer border-t border-surface-600/70 transition-colors hover:bg-surface-800/45"
                  onClick={() =>
                    navigate({
                      to: "/techniques/$techniqueId",
                      params: { techniqueId: technique.technique_id },
                    })
                  }
                  onKeyDown={(event) => {
                    if (event.key !== "Enter" && event.key !== " ") return

                    navigate({
                      to: "/techniques/$techniqueId",
                      params: { techniqueId: technique.technique_id },
                    })
                  }}
                  tabIndex={0}
                >
                  <td className="px-4 py-3 font-mono text-accent-glow">
                    {technique.technique_id}
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
                          ? "rounded-md border border-accent-primary/40 bg-accent-primary/12 px-2 py-1 text-xs text-accent-glow"
                          : "text-ink-muted"
                      }
                    >
                      {technique.pending_approval ? "Pending" : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-ink-secondary">
                    {technique.rule_confidence !== null
                      ? `${Math.round(technique.rule_confidence * 100)}%`
                      : "—"}
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
          {isDetailOpen ? (
            <Outlet />
          ) : (
            <p className="text-sm text-ink-secondary">
              Select a technique row to inspect its profile and generated rule.
            </p>
          )}
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
