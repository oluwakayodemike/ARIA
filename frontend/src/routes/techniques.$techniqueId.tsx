import { createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { ApiError, api } from "../api/client"
import { getErrorMessage } from "../lib/errors"
import { queryKeys } from "../lib/queryKeys"

export const Route = createFileRoute("/techniques/$techniqueId")({
  component: TechniqueDetailPage,
})

type AttackProfileShape = {
  severity?: string
  tactics?: string[]
  keywords?: string[]
  log_hints?: string[]
  description?: string
  detection_hint?: string
}

function TechniqueDetailPage() {
  const { techniqueId } = Route.useParams()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.technique(techniqueId),
    queryFn: () => api.getTechnique(techniqueId),
    retry: false,
    refetchInterval: 5000,
  })

  if (isLoading) {
    return <p className="text-ink-secondary">Loading technique details…</p>
  }

  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <p className="text-ink-secondary">
          Technique{" "}
          <span className="font-mono text-accent-glow">{techniqueId}</span> was
          not found in the current run.
        </p>
      )
    }

    return (
      <p className="text-verdict-gap">
        {getErrorMessage(error, "Failed to load technique details")}
      </p>
    )
  }

  if (!data) {
    return <p className="text-ink-secondary">Technique not found.</p>
  }

  const profile = (data.attack_profile ?? null) as AttackProfileShape | null

  return (
    <section className="space-y-4">
      <header className="space-y-2">
        <p className="muted-label">Technique Detail</p>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-mono text-xl text-accent-glow">
            {data.technique_id}
          </h2>
          <span className={statusBadgeClass(data)}>{statusLabel(data)}</span>
        </div>
        <p className="text-sm text-ink-secondary">{data.technique_name}</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        <InfoPair label="Verdict" value={data.verdict} />
        <InfoPair label="Tactics" value={data.tactics.join(", ") || "N/A"} />
        <InfoPair
          label="Rules enabled / total"
          value={`${data.enabled_rules}/${data.total_rules}`}
        />
        <InfoPair
          label="Confidence"
          value={
            data.rule_confidence !== null
              ? `${Math.round(data.rule_confidence * 100)}%`
              : "N/A"
          }
        />
      </div>

      <div className="space-y-2 rounded-lg border border-surface-600/70 bg-surface-800/70 p-3">
        <p className="muted-label">Attack Profile</p>

        {!profile ? (
          <p className="text-sm text-ink-secondary">
            No attack profile generated for this technique yet.
          </p>
        ) : (
          <div className="space-y-2 text-sm">
            <InfoPair label="Severity" value={profile.severity ?? "N/A"} />
            <InfoPair
              label="Profile tactics"
              value={profile.tactics?.join(", ") || "N/A"}
            />
            <InfoPair
              label="Keywords"
              value={profile.keywords?.join(", ") || "N/A"}
            />
            <InfoPair
              label="Log hints"
              value={profile.log_hints?.join(", ") || "N/A"}
            />
            <InfoPair
              label="Description"
              value={profile.description || "N/A"}
              multiline
            />
            <InfoPair
              label="Detection hint"
              value={profile.detection_hint || "N/A"}
              multiline
            />
          </div>
        )}
      </div>

      <div className="space-y-2 rounded-lg border border-surface-600/70 bg-surface-800/70 p-3">
        <p className="muted-label">Generated Rule</p>

        {data.rule_explanation ? (
          <p className="text-sm text-ink-secondary">{data.rule_explanation}</p>
        ) : (
          <p className="text-sm text-ink-secondary">
            No rule explanation is available yet.
          </p>
        )}

        {data.generated_rule ? (
          <pre className="scroll-soft max-h-[36vh] whitespace-pre-wrap rounded-lg border border-surface-600/70 bg-surface-900/80 p-3 text-xs text-ink-primary">
            {data.generated_rule}
          </pre>
        ) : (
          <p className="text-sm text-ink-secondary">No rule generated yet.</p>
        )}
      </div>
    </section>
  )
}

function InfoPair({
  label,
  value,
  multiline = false,
}: {
  label: string
  value: string
  multiline?: boolean
}) {
  return (
    <div>
      <p className="text-xs text-ink-muted">{label}</p>
      <p
        className={multiline ? "mt-1 text-sm text-ink-primary" : "mt-1 text-sm"}
      >
        {value}
      </p>
    </div>
  )
}

function statusLabel(technique: {
  pending_approval: boolean
  approved: boolean
  rejected: boolean
  deployed: boolean
}) {
  if (technique.pending_approval) return "Pending approval"
  if (technique.deployed) return "Deployed"
  if (technique.approved) return "Approved"
  if (technique.rejected) return "Rejected"
  return "Not staged"
}

function statusBadgeClass(technique: {
  pending_approval: boolean
  approved: boolean
  rejected: boolean
  deployed: boolean
}) {
  if (technique.pending_approval) {
    return "rounded-md border border-accent-primary/45 bg-accent-primary/14 px-2 py-1 text-xs text-accent-glow"
  }

  if (technique.deployed || technique.approved) {
    return "rounded-md border border-verdict-covered/45 bg-verdict-covered/14 px-2 py-1 text-xs text-verdict-covered"
  }

  if (technique.rejected) {
    return "rounded-md border border-verdict-gap/45 bg-verdict-gap/14 px-2 py-1 text-xs text-verdict-gap"
  }

  return "rounded-md border border-surface-600/70 bg-surface-700/70 px-2 py-1 text-xs text-ink-secondary"
}
